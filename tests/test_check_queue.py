"""Concurrency, fairness, recovery, and backpressure for the check queue."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from tests.conftest import ScriptedCapturer, create_org

from driftwatch.api.sites import _bounded
from driftwatch.check_queue import (
    CheckQueueFull,
    ClaimedCheckJob,
    DueSite,
    SiteCheckBusy,
    cancel_unrunnable_checks,
    check_queue_metrics,
    claim_next_check,
    complete_check,
    enqueue_and_claim_manual,
    enqueue_scheduled_checks,
    fail_check,
    prune_check_jobs,
    redrive_dead_check,
)
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.enums import CheckJobKind, CheckJobSource, CheckJobStatus
from driftwatch.exceptions import ConflictError, NotFoundError
from driftwatch.models import Organization, Site, SiteCheckJob
from driftwatch.monitoring.pipeline import CheckStatus
from driftwatch.runner import RunResult, SiteRunner
from driftwatch.scheduler import MonitorScheduler


async def _seed_sites(
    database: Database, counts: tuple[int, ...]
) -> tuple[list[int], list[list[int]]]:
    organization_ids: list[int] = []
    site_ids: list[list[int]] = []
    async with database.session() as session:
        for org_index, count in enumerate(counts):
            organization_id = await create_org(session, f"Organization {org_index}")
            organization_ids.append(organization_id)
            sites = [
                Site(
                    url=f"https://org-{org_index}-site-{site_index}.test",
                    organization_id=organization_id,
                )
                for site_index in range(count)
            ]
            session.add_all(sites)
            await session.flush()
            site_ids.append([site.id for site in sites])
        await session.commit()
    return organization_ids, site_ids


async def _enqueue(
    database: Database,
    candidates: list[DueSite],
    *,
    now: datetime,
    limit: int = 100,
    global_capacity: int = 1_000,
    per_org_capacity: int = 100,
) -> list[int]:
    async with database.session() as session:
        jobs = await enqueue_scheduled_checks(
            session,
            candidates,
            now=now,
            limit=limit,
            global_capacity=global_capacity,
            per_org_capacity=per_org_capacity,
        )
        await session.commit()
        return jobs


async def _claim(
    database: Database, now: datetime, *, lease_seconds: int = 30
) -> ClaimedCheckJob | None:
    async with database.session() as session:
        return await claim_next_check(session, now=now, lease_seconds=lease_seconds)


async def test_concurrent_claim_leases_a_job_once(database: Database) -> None:
    organization_ids, site_ids = await _seed_sites(database, (1,))
    now = datetime.now(UTC)
    job_ids = await _enqueue(
        database,
        [DueSite(site_ids[0][0], organization_ids[0], None)],
        now=now,
    )

    claims = await asyncio.gather(_claim(database, now), _claim(database, now))

    claimed = [claim for claim in claims if claim is not None]
    assert len(claimed) == 1
    assert claimed[0].id == job_ids[0]
    async with database.session() as session:
        row = await session.get(SiteCheckJob, job_ids[0])
        assert row is not None
        assert row.status == CheckJobStatus.RUNNING
        assert row.attempt_count == 1


async def test_manual_and_scheduled_checks_share_one_site_lock(database: Database) -> None:
    organization_ids, site_ids = await _seed_sites(database, (2,))
    now = datetime.now(UTC)
    await _enqueue(
        database,
        [DueSite(site_ids[0][0], organization_ids[0], None)],
        now=now,
    )

    async with database.session() as session:
        with pytest.raises(SiteCheckBusy):
            await enqueue_and_claim_manual(
                session,
                site_ids[0][0],
                kind=CheckJobKind.CHECK,
                analyze=True,
                now=now,
                lease_seconds=30,
                global_capacity=10,
                per_org_capacity=10,
            )
        await session.rollback()

    async with database.session() as session:
        await enqueue_and_claim_manual(
            session,
            site_ids[0][1],
            kind=CheckJobKind.SNAPSHOT,
            analyze=False,
            now=now,
            lease_seconds=30,
            global_capacity=10,
            per_org_capacity=10,
        )
        await session.commit()

    assert (
        await _enqueue(
            database,
            [DueSite(site_ids[0][1], organization_ids[0], None)],
            now=now,
        )
        == []
    )


async def test_parallel_manual_request_returns_conflict(
    admin_client: httpx.AsyncClient,
    capturer: ScriptedCapturer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_capture(*, url: str, **_: object) -> str:
        started.set()
        await release.wait()
        return "<main>captured</main>"

    monkeypatch.setattr(capturer, "capture", blocked_capture)
    created = await admin_client.post("/api/sites", json={"url": "https://parallel-manual.test"})
    site_id = created.json()["id"]
    first_request = asyncio.create_task(admin_client.post(f"/api/sites/{site_id}/check"))
    await asyncio.wait_for(started.wait(), timeout=1)
    try:
        conflict = await admin_client.post(f"/api/sites/{site_id}/check")
        assert conflict.status_code == 409
    finally:
        release.set()
    assert (await first_request).status_code == 200


async def test_enqueue_and_claim_are_fair_across_tenants(database: Database) -> None:
    organization_ids, site_ids = await _seed_sites(database, (3, 2))
    now = datetime.now(UTC)
    candidates = [
        *[DueSite(site_id, organization_ids[0], None) for site_id in site_ids[0]],
        *[DueSite(site_id, organization_ids[1], None) for site_id in site_ids[1]],
    ]

    await _enqueue(database, candidates, now=now)
    async with database.session() as session:
        enqueued_orgs = list(
            (
                await session.execute(
                    select(SiteCheckJob.organization_id).order_by(SiteCheckJob.id)
                )
            ).scalars()
        )
    assert enqueued_orgs == [
        organization_ids[0],
        organization_ids[1],
        organization_ids[0],
        organization_ids[1],
        organization_ids[0],
    ]

    claimed_orgs: list[int] = []
    for offset in range(5):
        claimed_at = now + timedelta(seconds=offset)
        job = await _claim(database, claimed_at)
        assert job is not None
        claimed_orgs.append(job.organization_id)
        async with database.session() as session:
            assert await complete_check(session, job, result={}, now=claimed_at)

    assert claimed_orgs == enqueued_orgs


async def test_expired_lease_is_recovered_after_worker_crash(database: Database) -> None:
    organization_ids, site_ids = await _seed_sites(database, (1,))
    now = datetime.now(UTC)
    [job_id] = await _enqueue(
        database,
        [DueSite(site_ids[0][0], organization_ids[0], None)],
        now=now,
    )
    first = await _claim(database, now, lease_seconds=30)
    assert first is not None

    assert await _claim(database, now + timedelta(seconds=29)) is None
    recovered = await _claim(database, now + timedelta(seconds=31))

    assert recovered is not None
    assert recovered.id == job_id
    assert recovered.attempt_count == 2
    assert recovered.lease_token != first.lease_token


async def test_failures_back_off_then_move_to_dead_letter(database: Database) -> None:
    organization_ids, site_ids = await _seed_sites(database, (1,))
    now = datetime.now(UTC)
    [job_id] = await _enqueue(
        database,
        [DueSite(site_ids[0][0], organization_ids[0], None)],
        now=now,
    )

    first = await _claim(database, now)
    assert first is not None
    async with database.session() as session:
        assert (
            await fail_check(
                session,
                first,
                error="first failure",
                now=now,
                max_attempts=3,
            )
            == CheckJobStatus.PENDING
        )
        row = await session.get(SiteCheckJob, job_id)
        assert row is not None and row.available_at is not None
        first_retry_at = row.available_at.replace(tzinfo=UTC)
    assert first_retry_at == now + timedelta(seconds=60)
    assert await _claim(database, now + timedelta(seconds=59)) is None

    second = await _claim(database, now + timedelta(seconds=60))
    assert second is not None and second.attempt_count == 2
    async with database.session() as session:
        assert (
            await fail_check(
                session,
                second,
                error="second failure",
                now=now + timedelta(seconds=60),
                max_attempts=3,
            )
            == CheckJobStatus.PENDING
        )
        row = await session.get(SiteCheckJob, job_id)
        assert row is not None and row.available_at is not None
        second_retry_at = row.available_at.replace(tzinfo=UTC)
    assert second_retry_at == now + timedelta(seconds=360)

    third = await _claim(database, now + timedelta(seconds=360))
    assert third is not None and third.attempt_count == 3
    async with database.session() as session:
        assert (
            await fail_check(
                session,
                third,
                error="final failure",
                now=now + timedelta(seconds=360),
                max_attempts=3,
            )
            == CheckJobStatus.DEAD
        )
        row = await session.get(SiteCheckJob, job_id)
        assert row is not None
        assert row.status == CheckJobStatus.DEAD
        assert row.available_at is None
        assert row.lease_token is None
        metrics = await check_queue_metrics(session, now=now + timedelta(seconds=360))
    assert metrics.dead == 1
    assert metrics.active == 0


async def test_queue_caps_apply_globally_and_per_tenant(database: Database) -> None:
    organization_ids, site_ids = await _seed_sites(database, (2, 1, 1))
    now = datetime.now(UTC)
    inserted = await _enqueue(
        database,
        [
            DueSite(site_ids[0][0], organization_ids[0], None),
            DueSite(site_ids[0][1], organization_ids[0], None),
            DueSite(site_ids[1][0], organization_ids[1], None),
        ],
        now=now,
        global_capacity=2,
        per_org_capacity=1,
    )
    assert len(inserted) == 2

    async with database.session() as session:
        with pytest.raises(CheckQueueFull, match="queue is at capacity"):
            await enqueue_and_claim_manual(
                session,
                site_ids[2][0],
                kind=CheckJobKind.CHECK,
                analyze=True,
                now=now,
                lease_seconds=30,
                global_capacity=2,
                per_org_capacity=1,
            )
        await session.rollback()
        metrics = await check_queue_metrics(session, now=now)
    assert metrics.pending == 2
    assert metrics.oldest_pending_seconds == 0


async def test_terminal_job_retention_includes_dead_letters(database: Database) -> None:
    organization_ids, site_ids = await _seed_sites(database, (1,))
    now = datetime.now(UTC)
    async with database.session() as session:
        session.add_all(
            [
                SiteCheckJob(
                    organization_id=organization_ids[0],
                    site_id=site_ids[0][0],
                    idempotency_key=f"retention-{status}-{age}",
                    kind=CheckJobKind.CHECK,
                    source=CheckJobSource.SCHEDULED,
                    analyze=True,
                    status=status,
                    attempt_count=1,
                    available_at=None,
                    enqueued_at=now - timedelta(days=age),
                    completed_at=now - timedelta(days=age),
                )
                for status, age in (
                    (CheckJobStatus.DEAD, 31),
                    (CheckJobStatus.SUCCEEDED, 31),
                    (CheckJobStatus.DEAD, 29),
                )
            ]
        )
        await session.commit()

    async with database.session() as session:
        assert await prune_check_jobs(session, older_than_days=30, now=now) == 2
        await session.commit()
        statuses = list((await session.execute(select(SiteCheckJob.status))).scalars())
    assert statuses == [CheckJobStatus.DEAD]


async def test_expired_ineligible_job_releases_the_site_lock(database: Database) -> None:
    organization_ids, site_ids = await _seed_sites(database, (1,))
    now = datetime.now(UTC)
    [job_id] = await _enqueue(
        database,
        [DueSite(site_ids[0][0], organization_ids[0], None)],
        now=now,
    )
    assert await _claim(database, now, lease_seconds=30) is not None
    async with database.session() as session:
        organization = await session.get(Organization, organization_ids[0])
        assert organization is not None
        organization.is_active = False
        await session.commit()

    async with database.session() as session:
        cancelled = await cancel_unrunnable_checks(session, now=now + timedelta(seconds=31))
        await session.commit()
        row = await session.get(SiteCheckJob, job_id)
    assert cancelled == 1
    assert row is not None
    assert row.status == CheckJobStatus.CANCELLED
    assert row.lease_token is None


class _BlockingRunner:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def run(self, site_id: int, *, analyze: bool = True) -> RunResult:
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def snapshot(self, site_id: int) -> RunResult:
        return await self.run(site_id, analyze=False)


class _CaptureFailureRunner:
    async def run(self, site_id: int, *, analyze: bool = True) -> RunResult:
        return RunResult(
            site_id,
            CheckStatus.UNCHANGED,
            capture_error="failed https://user:secret@example.test/?token=private\n" + "x" * 800,
        )

    async def snapshot(self, site_id: int) -> RunResult:
        return await self.run(site_id, analyze=False)


class _AnalysisFailureRunner:
    async def run(self, site_id: int, *, analyze: bool = True) -> RunResult:
        return RunResult(
            site_id,
            CheckStatus.CHANGED,
            ai_error="provider rejected https://user:secret@example.test/?token=private",
        )

    async def snapshot(self, site_id: int) -> RunResult:
        return await self.run(site_id, analyze=False)


async def test_cancelled_manual_job_is_durably_retried(
    database: Database, settings: Settings
) -> None:
    _, site_ids = await _seed_sites(database, (1,))
    runner = _BlockingRunner()
    scheduler = MonitorScheduler(database, cast(SiteRunner, runner), settings)
    task = asyncio.create_task(scheduler.run_manual_check(site_ids[0][0]))
    await asyncio.wait_for(runner.started.wait(), timeout=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    async with database.session() as session:
        row = (
            await session.execute(select(SiteCheckJob).order_by(SiteCheckJob.id.desc()))
        ).scalar_one()
    assert row.status == CheckJobStatus.PENDING
    assert row.lease_token is None
    assert row.last_error == "check cancelled before completion"


async def test_manual_timeout_releases_lease_and_returns_gateway_timeout(
    database: Database, settings: Settings
) -> None:
    _, site_ids = await _seed_sites(database, (1,))
    runner = _BlockingRunner()
    scheduler = MonitorScheduler(database, cast(SiteRunner, runner), settings)
    settings.per_site_budget_seconds = 0.2

    with pytest.raises(HTTPException) as error:
        await _bounded(scheduler.run_manual_check(site_ids[0][0]), settings)

    assert error.value.status_code == 504
    assert runner.started.is_set()
    async with database.session() as session:
        row = (
            await session.execute(select(SiteCheckJob).order_by(SiteCheckJob.id.desc()))
        ).scalar_one()
    assert row.status == CheckJobStatus.PENDING
    assert row.lease_token is None


async def test_capture_failure_is_redacted_in_durable_queue(
    database: Database, settings: Settings
) -> None:
    _, site_ids = await _seed_sites(database, (1,))
    runner = _CaptureFailureRunner()
    scheduler = MonitorScheduler(database, cast(SiteRunner, runner), settings)

    result = await scheduler.run_manual_check(site_ids[0][0])

    assert result.capture_error is not None
    async with database.session() as session:
        row = (
            await session.execute(select(SiteCheckJob).order_by(SiteCheckJob.id.desc()))
        ).scalar_one()
    assert row.last_error == "CaptureError: capture failed"
    assert "secret" not in row.last_error
    assert len(row.last_error) <= 500


async def test_analysis_failure_is_redacted_in_durable_result(
    database: Database, settings: Settings
) -> None:
    _, site_ids = await _seed_sites(database, (1,))
    scheduler = MonitorScheduler(
        database,
        cast(SiteRunner, _AnalysisFailureRunner()),
        settings,
    )

    await scheduler.run_manual_check(site_ids[0][0])

    async with database.session() as session:
        row = (
            await session.execute(select(SiteCheckJob).order_by(SiteCheckJob.id.desc()))
        ).scalar_one()
    assert row.result is not None
    assert row.result["ai_error"] == "AIError: analysis failed"
    assert row.result["capture_error"] is None
    assert "secret" not in str(row.result)


async def test_successful_manual_check_creates_a_new_scheduled_generation(
    database: Database, settings: Settings
) -> None:
    organization_ids, site_ids = await _seed_sites(database, (1,))
    site_id = site_ids[0][0]
    now = datetime.now(UTC)
    [dead_job_id] = await _enqueue(
        database,
        [DueSite(site_id, organization_ids[0], None)],
        now=now,
    )
    dead = await _claim(database, now)
    assert dead is not None
    async with database.session() as session:
        assert (
            await fail_check(
                session,
                dead,
                error="exhausted",
                now=now,
                max_attempts=1,
            )
            == CheckJobStatus.DEAD
        )

    runner = SiteRunner(database, ScriptedCapturer(html="<main>recovered</main>"), settings)
    scheduler = MonitorScheduler(database, runner, settings)
    result = await scheduler.run_manual_check(site_id, analyze=False)
    assert result.status == CheckStatus.BASELINE

    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None and site.last_checked_at is not None
        marker = site.last_checked_at
    [new_job_id] = await _enqueue(
        database,
        [DueSite(site_id, organization_ids[0], marker)],
        now=now + timedelta(minutes=1),
    )

    assert new_job_id != dead_job_id
    async with database.session() as session:
        keys = list(
            (
                await session.execute(
                    select(SiteCheckJob.idempotency_key)
                    .where(SiteCheckJob.source == "scheduled")
                    .order_by(SiteCheckJob.id)
                )
            ).scalars()
        )
    assert keys[0].endswith(":never")
    assert keys[1] != keys[0]


async def test_redrive_is_idempotent_and_only_the_latest_dead_generation_is_open(
    database: Database,
) -> None:
    organization_ids, site_ids = await _seed_sites(database, (1,))
    organization_id = organization_ids[0]
    site_id = site_ids[0][0]
    now = datetime.now(UTC)
    async with database.session() as session:
        original = SiteCheckJob(
            organization_id=organization_id,
            site_id=site_id,
            idempotency_key="scheduled:redrive-original:never",
            kind=CheckJobKind.CHECK,
            source=CheckJobSource.SCHEDULED,
            analyze=False,
            status=CheckJobStatus.DEAD,
            attempt_count=5,
            available_at=None,
            enqueued_at=now - timedelta(hours=1),
            completed_at=now - timedelta(minutes=30),
            last_error="private upstream diagnostic",
        )
        session.add(original)
        await session.commit()
        original_id = original.id

    async with database.session() as session:
        child, created = await redrive_dead_check(
            session,
            original_id,
            organization_id=organization_id,
            request_key="incident-redrive-001",
            request_sha256="a" * 64,
            now=now,
            global_capacity=10,
            per_org_capacity=10,
        )
        await session.commit()
        child_id = child.id
    assert created is True

    async with database.session() as session:
        replay, replay_created = await redrive_dead_check(
            session,
            original_id,
            organization_id=organization_id,
            request_key="incident-redrive-001",
            request_sha256="a" * 64,
            now=now + timedelta(seconds=1),
            global_capacity=10,
            per_org_capacity=10,
        )
        await session.commit()
        assert replay.id == child_id
        assert replay_created is False

    async with database.session() as session:
        with pytest.raises(ConflictError, match="another request"):
            await redrive_dead_check(
                session,
                original_id,
                organization_id=organization_id,
                request_key="incident-redrive-001",
                request_sha256="b" * 64,
                now=now,
                global_capacity=10,
                per_org_capacity=10,
            )
        await session.rollback()
    async with database.session() as session:
        with pytest.raises(ConflictError, match="already been redriven"):
            await redrive_dead_check(
                session,
                original_id,
                organization_id=organization_id,
                request_key="incident-redrive-002",
                request_sha256="a" * 64,
                now=now,
                global_capacity=10,
                per_org_capacity=10,
            )
        await session.rollback()

    async with database.session() as session:
        original = await session.get(SiteCheckJob, original_id)
        child = await session.get(SiteCheckJob, child_id)
        assert original is not None and child is not None
        assert original.status == CheckJobStatus.DEAD
        assert original.last_error == "private upstream diagnostic"
        assert child.original_job_id == original.id
        assert child.source == CheckJobSource.REDRIVE
        assert child.kind == original.kind
        assert child.analyze is False
        metrics = await check_queue_metrics(session, now=now)
        assert (metrics.pending, metrics.dead) == (1, 0)

        child.status = CheckJobStatus.DEAD
        child.available_at = None
        child.completed_at = now
        await session.commit()

    async with database.session() as session:
        metrics = await check_queue_metrics(session, now=now)
        assert (metrics.pending, metrics.dead) == (0, 1)


async def test_redrive_checks_tenant_liveness_site_state_and_capacity(
    database: Database,
) -> None:
    organization_ids, site_ids = await _seed_sites(database, (2, 1))
    organization_id = organization_ids[0]
    site_id, busy_site_id = site_ids[0]
    now = datetime.now(UTC)
    async with database.session() as session:
        dead = SiteCheckJob(
            organization_id=organization_id,
            site_id=site_id,
            idempotency_key="scheduled:redrive-guards:never",
            kind=CheckJobKind.CHECK,
            source=CheckJobSource.SCHEDULED,
            analyze=True,
            status=CheckJobStatus.DEAD,
            attempt_count=5,
            available_at=None,
            enqueued_at=now,
            completed_at=now,
        )
        session.add(dead)
        await session.flush()
        dead_id = dead.id
        await session.commit()

    async with database.session() as session:
        with pytest.raises(NotFoundError):
            await redrive_dead_check(
                session,
                dead_id,
                organization_id=organization_ids[1],
                request_key="wrong-tenant-001",
                request_sha256="a" * 64,
                now=now,
                global_capacity=10,
                per_org_capacity=10,
            )
        await session.rollback()

    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        site.enabled = False
        await session.commit()
    async with database.session() as session:
        with pytest.raises(ConflictError, match="site must be enabled"):
            await redrive_dead_check(
                session,
                dead_id,
                organization_id=organization_id,
                request_key="disabled-site-001",
                request_sha256="a" * 64,
                now=now,
                global_capacity=10,
                per_org_capacity=10,
            )
        await session.rollback()

    async with database.session() as session:
        site = await session.get(Site, site_id)
        organization = await session.get(Organization, organization_id)
        assert site is not None and organization is not None
        site.enabled = True
        organization.is_active = False
        await session.commit()
    async with database.session() as session:
        with pytest.raises(ConflictError, match="organization must be active"):
            await redrive_dead_check(
                session,
                dead_id,
                organization_id=organization_id,
                request_key="inactive-org-001",
                request_sha256="a" * 64,
                now=now,
                global_capacity=10,
                per_org_capacity=10,
            )
        await session.rollback()

    async with database.session() as session:
        organization = await session.get(Organization, organization_id)
        assert organization is not None
        organization.is_active = True
        session.add(
            SiteCheckJob(
                organization_id=organization_id,
                site_id=busy_site_id,
                idempotency_key="manual:redrive-capacity:test",
                kind=CheckJobKind.CHECK,
                source=CheckJobSource.MANUAL,
                analyze=True,
                status=CheckJobStatus.RUNNING,
                attempt_count=1,
                available_at=None,
                lease_token="redrive-capacity-lease",
                lease_expires_at=now + timedelta(minutes=1),
                enqueued_at=now,
            )
        )
        await session.commit()
    async with database.session() as session:
        with pytest.raises(CheckQueueFull, match="at capacity"):
            await redrive_dead_check(
                session,
                dead_id,
                organization_id=organization_id,
                request_key="full-queue-001",
                request_sha256="a" * 64,
                now=now,
                global_capacity=1,
                per_org_capacity=10,
            )
        await session.rollback()

    with pytest.raises(ValueError, match="hexadecimal"):
        async with database.session() as session:
            await redrive_dead_check(
                session,
                dead_id,
                organization_id=organization_id,
                request_key="invalid-digest-001",
                request_sha256="not-a-digest",
                now=now,
                global_capacity=10,
                per_org_capacity=10,
            )

    async with database.session() as session:
        busy = await session.scalar(
            select(SiteCheckJob).where(
                SiteCheckJob.idempotency_key == "manual:redrive-capacity:test"
            )
        )
        assert busy is not None
        await session.delete(busy)
        await session.commit()
    async with database.session() as session:
        child, _ = await redrive_dead_check(
            session,
            dead_id,
            organization_id=organization_id,
            request_key="cancel-disabled-redrive-001",
            request_sha256="a" * 64,
            now=now,
            global_capacity=10,
            per_org_capacity=10,
        )
        await session.commit()
        child_id = child.id
    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        site.enabled = False
        await session.commit()
    async with database.session() as session:
        assert await cancel_unrunnable_checks(session, now=now) == 1
        await session.commit()
        child = await session.get(SiteCheckJob, child_id)
        assert child is not None
        assert child.status == CheckJobStatus.CANCELLED


async def test_pruning_an_old_original_preserves_a_live_redrive_child(
    database: Database,
) -> None:
    organization_ids, site_ids = await _seed_sites(database, (1,))
    now = datetime.now(UTC)
    async with database.session() as session:
        original = SiteCheckJob(
            organization_id=organization_ids[0],
            site_id=site_ids[0][0],
            idempotency_key="scheduled:retained-redrive:never",
            kind=CheckJobKind.CHECK,
            source=CheckJobSource.SCHEDULED,
            analyze=True,
            status=CheckJobStatus.DEAD,
            attempt_count=5,
            available_at=None,
            enqueued_at=now - timedelta(days=40),
            completed_at=now - timedelta(days=31),
        )
        session.add(original)
        await session.flush()
        child = SiteCheckJob(
            organization_id=organization_ids[0],
            site_id=site_ids[0][0],
            original_job_id=original.id,
            redrive_request_sha256="c" * 64,
            idempotency_key="redrive:retained-child",
            kind=CheckJobKind.CHECK,
            source=CheckJobSource.REDRIVE,
            analyze=True,
            status=CheckJobStatus.PENDING,
            attempt_count=0,
            available_at=now,
            enqueued_at=now,
        )
        session.add(child)
        await session.commit()
        original_id = original.id
        child_id = child.id

    async with database.session() as session:
        assert await prune_check_jobs(session, older_than_days=30, now=now) == 1
        await session.commit()

    async with database.session() as session:
        assert await session.get(SiteCheckJob, original_id) is None
        child = await session.get(SiteCheckJob, child_id)
        assert child is not None
        assert child.original_job_id is None
        assert child.redrive_request_sha256 == "c" * 64
        assert child.status == CheckJobStatus.PENDING
