"""Account-message ownership across hard crashes, deadlines and slow batches."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from driftwatch.account_mail import (
    AccountEmailWorker,
    _claim_next,
    _DeliveryResult,
    _finish,
    enqueue_account_invitation,
)
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.enums import AccountEmailStatus, EmailChannelName
from driftwatch.models import AccountEmailJob, Organization, User
from driftwatch.notifications.email import EmailEnvelope


@dataclass
class Clock:
    value: datetime

    def __call__(self) -> datetime:
        return self.value


async def seed_job(database: Database, *, now: datetime, suffix: int = 1) -> tuple[int, int]:
    async with database.session() as session:
        organization = Organization(name=f"Owned fixture {suffix}")
        session.add(organization)
        await session.flush()
        user = User(
            email=f"lease-{suffix}@example.com",
            password_hash="unused fixture",
            organization_id=organization.id,
        )
        session.add(user)
        await session.flush()
        job, created = await enqueue_account_invitation(session, user=user, now=now)
        assert created
        await session.commit()
        return job.id, user.id


async def test_hard_crashes_stop_at_budget_and_release_active_invitation(
    database: Database,
) -> None:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    job_id, user_id = await seed_job(database, now=now)
    for attempt in range(1, 6):
        async with database.session() as session:
            claimed = await _claim_next(session, now=now, lease_seconds=10)
        assert claimed is not None and claimed.attempt_count == attempt
        # A hard crash never calls _finish; only the next claimant observes expiry.
        now += timedelta(seconds=10)
    async with database.session() as session:
        assert await _claim_next(session, now=now, lease_seconds=10) is None
        job = await session.get(AccountEmailJob, job_id)
        assert job is not None
        assert job.status == AccountEmailStatus.FAILED and job.attempt_count == 5
        assert job.active_key is None and job.lease_token is None
        assert job.next_attempt_at is None and job.finished_at is not None
        assert job.last_error_code == "attempt_budget_exhausted"
        user = await session.get(User, user_id)
        assert user is not None
        replacement, created = await enqueue_account_invitation(session, user=user, now=now)
        assert created and replacement.id != job_id


async def test_expired_finish_cannot_save_provider_acceptance_or_new_owners_token(
    database: Database,
) -> None:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    job_id, _ = await seed_job(database, now=now)
    async with database.session() as session:
        old = await _claim_next(session, now=now, lease_seconds=10)
    assert old is not None
    accepted = _DeliveryResult(state="sent", provider_message_id="owned-fixture")
    expires = now + timedelta(seconds=10)
    async with database.session() as session:
        assert not await _finish(session, old, accepted, now=expires)
        replacement = await _claim_next(session, now=expires, lease_seconds=10)
    assert replacement is not None and replacement.lease_token != old.lease_token
    async with database.session() as session:
        assert not await _finish(session, old, accepted, now=expires + timedelta(seconds=1))
        job = await session.get(AccountEmailJob, job_id)
        assert job is not None and job.status == AccountEmailStatus.PENDING
        assert job.lease_token == replacement.lease_token and job.provider_message_id is None
        assert await _finish(session, replacement, accepted, now=expires + timedelta(seconds=1))


async def test_slow_batch_claims_and_finishes_each_message_with_current_clock(
    database: Database, settings: Settings
) -> None:
    clock = Clock(datetime(2026, 10, 1, tzinfo=UTC))
    for index in range(3):
        await seed_job(database, now=clock(), suffix=index)

    class SlowChannel:
        name = EmailChannelName.BREVO
        calls = 0

        async def send(self, envelope: EmailEnvelope) -> str:
            self.calls += 1
            clock.value += timedelta(seconds=9)
            await asyncio.sleep(0)
            return "fixture-message"

    channel = SlowChannel()
    worker = AccountEmailWorker(database, settings, channel=channel)
    assert await worker.drain(limit=3, lease_seconds=10, clock=clock) == 3
    assert channel.calls == 3
    async with database.session() as session:
        jobs = list(
            (await session.execute(select(AccountEmailJob).order_by(AccountEmailJob.id))).scalars()
        )
        assert all(job.status == AccountEmailStatus.SENT and job.attempt_count == 1 for job in jobs)
        assert (jobs[2].delivered_at - jobs[0].delivered_at).total_seconds() == 18


async def test_whole_delivery_is_cancelled_before_lease_expires(
    database: Database, settings: Settings
) -> None:
    clock = Clock(datetime.now(UTC))
    job_id, _ = await seed_job(database, now=clock())
    started, cancelled = asyncio.Event(), asyncio.Event()

    class HangingChannel:
        name = EmailChannelName.BREVO

        async def send(self, envelope: EmailEnvelope) -> str:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
            return "unreachable"

    worker = AccountEmailWorker(database, settings, channel=HangingChannel())
    async with asyncio.timeout(3):
        assert await worker.drain(limit=1, lease_seconds=1, clock=clock) == 1
    assert started.is_set() and cancelled.is_set()
    async with database.session() as session:
        job = await session.get(AccountEmailJob, job_id)
        assert job is not None and job.status == AccountEmailStatus.PENDING
        assert job.last_error_code == "delivery_timeout" and job.lease_token is None


async def test_live_fifth_claim_is_not_exhausted_until_expiry(database: Database) -> None:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    job_id, _ = await seed_job(database, now=now)
    async with database.session() as session:
        job = await session.get(AccountEmailJob, job_id)
        assert job is not None
        job.attempt_count = 4
        await session.commit()
        claimed = await _claim_next(session, now=now, lease_seconds=10)
    assert claimed is not None and claimed.attempt_count == 5
    async with database.session() as session:
        assert await _claim_next(session, now=now + timedelta(seconds=9), lease_seconds=10) is None
        assert await _finish(
            session, claimed, _DeliveryResult(state="sent"), now=now + timedelta(seconds=9)
        )


async def test_clock_contract_rejects_conflicting_time_sources(
    database: Database, settings: Settings
) -> None:
    worker = AccountEmailWorker(database, settings)
    with pytest.raises(ValueError, match="frozen now"):
        await worker.drain(now=datetime.now(UTC), clock=lambda: datetime.now(UTC))
    with pytest.raises(ValueError, match="positive"):
        await worker.drain(lease_seconds=0)
