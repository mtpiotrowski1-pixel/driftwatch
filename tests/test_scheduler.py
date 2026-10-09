"""Tests for due-site selection, retry sweeping, and scheduled backups."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from driftwatch.account_mail import AccountEmailWorker, enqueue_account_invitation
from driftwatch.api.health import _scheduler_is_stale
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.models import AccountEmailJob, ChangeEvent, Organization, Site, Snapshot, User
from driftwatch.monitoring.pipeline import clear_retry_state
from driftwatch.runner import SiteRunner
from driftwatch.scheduler import MonitorScheduler, find_changes_to_retry, find_due_sites
from tests.conftest import RecordingChannel, ScriptedCapturer, create_org


async def test_find_due_sites_selects_unchecked_and_overdue(database: Database) -> None:
    now = datetime.now(UTC)
    async with database.session() as session:
        org_id = await create_org(session)
        never_checked = Site(
            url="https://a.test", check_interval_minutes=60, organization_id=org_id
        )
        overdue = Site(
            url="https://b.test",
            check_interval_minutes=30,
            last_checked_at=now - timedelta(minutes=45),
            organization_id=org_id,
        )
        fresh = Site(
            url="https://c.test",
            check_interval_minutes=60,
            last_checked_at=now - timedelta(minutes=5),
            organization_id=org_id,
        )
        disabled = Site(
            url="https://d.test",
            enabled=False,
            check_interval_minutes=1,
            organization_id=org_id,
        )
        session.add_all([never_checked, overdue, fresh, disabled])
        await session.commit()
        ids = {never_checked.id, overdue.id}

    async with database.session() as session:
        due = set(await find_due_sites(session, now))
    assert due == ids


async def test_find_due_sites_excludes_suspended_organizations(database: Database) -> None:
    now = datetime.now(UTC)
    async with database.session() as session:
        active_org_id = await create_org(session, "Active")
        suspended_org_id = await create_org(session, "Suspended")
        suspended_org = await session.get(Organization, suspended_org_id)
        assert suspended_org is not None
        suspended_org.is_active = False
        active_site = Site(url="https://active.test", organization_id=active_org_id)
        suspended_site = Site(url="https://suspended.test", organization_id=suspended_org_id)
        session.add_all([active_site, suspended_site])
        await session.commit()
        active_id = active_site.id

    async with database.session() as session:
        due = await find_due_sites(session, now)

    assert due == [active_id]


async def test_resolved_change_is_not_retried_forever(database: Database) -> None:
    """A change that still carries a notification error but has been resolved
    (no scheduled retry) must not be re-selected on every tick."""
    now = datetime.now(UTC)
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(url="https://a.test", organization_id=org_id)
        session.add(site)
        await session.flush()
        snapshot = Snapshot(site_id=site.id, content_html="<p>x</p>", content_text="x")
        session.add(snapshot)
        await session.flush()
        change = ChangeEvent(
            site_id=site.id,
            new_snapshot_id=snapshot.id,
            notification_error="all recipient deliveries failed",
        )
        session.add(change)
        await session.commit()
        change_id = change.id

    # With no scheduled time the failing change is due immediately.
    async with database.session() as session:
        assert await find_changes_to_retry(session, now, limit=10) == [change_id]

    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        assert change is not None
        clear_retry_state(change)
        await session.commit()

    async with database.session() as session:
        assert await find_changes_to_retry(session, now, limit=10) == []


def _scheduler(database: Database, settings: Settings) -> MonitorScheduler:
    return MonitorScheduler(database, SiteRunner(database, ScriptedCapturer(), settings), settings)


def test_readiness_detects_a_stale_expected_scheduler(
    database: Database, settings: Settings
) -> None:
    scheduler = _scheduler(database, settings)
    now = datetime.now(UTC)
    assert _scheduler_is_stale(scheduler, settings, now) is False

    scheduler._expected = True
    scheduler._started_at = now - timedelta(minutes=10)
    assert _scheduler_is_stale(scheduler, settings, now) is True

    scheduler._last_tick_at = now
    assert _scheduler_is_stale(scheduler, settings, now) is False


def _age(path: Path, *, hours: float) -> None:
    stamp = (datetime.now(UTC) - timedelta(hours=hours)).timestamp()
    os.utime(path, (stamp, stamp))


async def test_tick_takes_one_backup_per_interval(database: Database, settings: Settings) -> None:
    scheduler = _scheduler(database, settings)
    backups = settings.data_dir / "backups"

    await scheduler.tick()
    files = sorted(backups.glob("test-*.db"))
    assert len(files) == 1
    assert scheduler.last_backup_at is not None
    assert scheduler.last_backup_file == files[0].name

    await scheduler.tick()  # the default 24h interval has not elapsed
    assert len(sorted(backups.glob("test-*.db"))) == 1


async def test_account_email_tick_drains_durable_queue_independently(
    database: Database,
    settings: Settings,
) -> None:
    async with database.session() as session:
        org_id = await create_org(session)
        user = User(
            email="scheduled-invite@example.com",
            password_hash="unusable-test-hash",
            organization_id=org_id,
        )
        session.add(user)
        await session.flush()
        await enqueue_account_invitation(session, user=user)
        await session.commit()

    channel = RecordingChannel()
    worker = AccountEmailWorker(database, settings, channel=channel)
    scheduler = MonitorScheduler(
        database,
        SiteRunner(database, ScriptedCapturer(), settings),
        settings,
        account_email_worker=worker,
    )
    await scheduler.account_email_tick()

    assert len(channel.sent) == 1
    assert channel.sent[0].to == "scheduled-invite@example.com"
    async with database.session() as session:
        job = (await session.execute(select(AccountEmailJob))).scalar_one()
        assert str(job.status) == "sent"


async def test_scheduler_registers_account_email_as_an_independent_job(
    database: Database,
    settings: Settings,
) -> None:
    scheduler = _scheduler(database, settings)
    scheduler.start()
    try:
        assert {job.id for job in scheduler._scheduler.get_jobs()} == {
            "driftwatch-account-email",
            "driftwatch-tick",
        }
    finally:
        scheduler.shutdown()


async def test_backup_rotation_caps_backups_and_pre_restore_copies(
    database: Database, settings: Settings
) -> None:
    settings.backup_keep_count = 2
    scheduler = _scheduler(database, settings)
    backups = settings.data_dir / "backups"
    backups.mkdir(parents=True)
    for day in (1, 2, 3):
        stale = backups / f"test-2020010{day}-000000.db"
        stale.write_bytes(b"old")
        _age(stale, hours=48)  # older than the interval, so a new backup is due
    for day in (1, 2, 3):
        (settings.data_dir / f"test-pre-restore-2020010{day}-000000.db").write_bytes(b"old")

    await scheduler.tick()

    remaining = sorted(path.name for path in backups.glob("test-*.db"))
    assert len(remaining) == 2
    assert remaining[0] == "test-20200103-000000.db"  # newest old backup survives
    assert scheduler.last_backup_file == remaining[1]
    pre_restore = sorted(path.name for path in settings.data_dir.glob("test-pre-restore-*.db"))
    assert pre_restore == [
        "test-pre-restore-20200102-000000.db",
        "test-pre-restore-20200103-000000.db",
    ]


async def test_backup_cadence_is_seeded_from_disk_after_restart(
    database: Database, settings: Settings
) -> None:
    """A fresh scheduler (as after a process restart) must honour a recent
    backup already on disk instead of taking a spurious new one."""
    backups = settings.data_dir / "backups"
    backups.mkdir(parents=True)
    recent = backups / "test-20260101-000000.db"
    recent.write_bytes(b"fresh")  # mtime is now

    scheduler = _scheduler(database, settings)
    await scheduler.tick()

    assert sorted(path.name for path in backups.glob("test-*.db")) == [recent.name]
    assert scheduler.last_backup_file == recent.name
    assert scheduler.last_backup_at is not None
