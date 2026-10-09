"""Periodic monitoring, account-email delivery, retention, and backups.

Monitoring and account-email delivery use independent ``AsyncIOScheduler``
jobs. A slow capture backlog therefore cannot consume the delivery latency of a
password reset or invitation. Both jobs are bounded and coordinated with the
maintenance lock before a database restore.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from anyio import to_thread
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.account_mail import AccountEmailWorker, prune_account_email_jobs
from driftwatch.billing.service import expire_billing_entitlements
from driftwatch.check_queue import (
    ClaimedCheckJob,
    DueSite,
    cancel_unrunnable_checks,
    claim_next_check,
    complete_check,
    enqueue_and_claim_manual,
    enqueue_scheduled_checks,
    fail_check,
    prune_check_jobs,
)
from driftwatch.config import Settings
from driftwatch.db import Database, snapshot_sqlite, sqlite_file_path
from driftwatch.enums import CheckJobKind
from driftwatch.models import ChangeEvent, Organization, Site
from driftwatch.retention import prune_ai_usage, prune_site_history
from driftwatch.runner import RunResult, SiteRunner
from driftwatch.security.crypto import SecretBox
from driftwatch.settings_store import SettingsStore

logger = logging.getLogger(__name__)

_ACCOUNT_EMAIL_BATCH_SIZE = 10


class MonitorScheduler:
    def __init__(
        self,
        db: Database,
        runner: SiteRunner,
        settings: Settings,
        *,
        account_email_worker: AccountEmailWorker | None = None,
    ) -> None:
        self._db = db
        self._runner = runner
        self._settings = settings
        self._account_email_worker = account_email_worker or AccountEmailWorker(db, settings)
        self._scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
        self._expected = False
        self._started_at: datetime | None = None
        self._last_tick_at: datetime | None = None
        self._last_backup_at: datetime | None = None
        self._last_backup_file: str | None = None
        self._tick_lock = asyncio.Lock()
        self._account_email_lock = asyncio.Lock()
        self._maintenance_paused = False

    @property
    def running(self) -> bool:
        return bool(self._scheduler.running)

    @property
    def expected(self) -> bool:
        """Whether this scheduler was started and should therefore be running."""
        return self._expected

    @property
    def last_tick_at(self) -> datetime | None:
        return self._last_tick_at

    @property
    def started_at(self) -> datetime | None:
        return self._started_at

    @property
    def last_backup_at(self) -> datetime | None:
        return self._last_backup_at

    @property
    def last_backup_file(self) -> str | None:
        return self._last_backup_file

    def start(self) -> None:
        self._scheduler.add_job(
            self.tick,
            "interval",
            seconds=self._settings.scheduler_tick_seconds,
            id="driftwatch-tick",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.add_job(
            self.account_email_tick,
            "interval",
            seconds=self._settings.scheduler_tick_seconds,
            id="driftwatch-account-email",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        self._expected = True
        self._started_at = datetime.now(UTC)
        logger.info("scheduler started; tick every %ss", self._settings.scheduler_tick_seconds)

    def shutdown(self) -> None:
        self._expected = False
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    async def tick(self) -> None:
        if self._maintenance_paused:
            return
        async with self._tick_lock:
            # A tick may have queued behind an already-running tick just before
            # maintenance was requested. Recheck after taking the lock so it
            # cannot start database work while a restore owns the lock.
            if self._maintenance_paused:
                return
            await self._run_tick()

    async def account_email_tick(self) -> None:
        """Drain a bounded mail batch independently of long-running captures."""
        if self._maintenance_paused:
            return
        async with self._account_email_lock:
            # Match ``tick()``: a call may have queued immediately before a
            # restore requested maintenance, so recheck after taking the lock.
            if self._maintenance_paused:
                return
            await self._deliver_account_email()

    async def _run_tick(self) -> None:
        self._last_tick_at = datetime.now(UTC)
        await self._refresh_billing_access()
        await self._check_due_sites()
        await self._retry_pending_changes()
        await self._prune_old_usage()
        try:
            await self._maybe_backup()
        except Exception:
            # A failed backup must never take the monitoring loop down with it;
            # it is retried on the next tick and visible in the log.
            logger.exception("scheduled database backup failed")

    async def _deliver_account_email(self) -> None:
        try:
            processed = await self._account_email_worker.drain(limit=_ACCOUNT_EMAIL_BATCH_SIZE)
        except Exception:
            # Delivery rows retain their lease and become eligible again after
            # expiry. A queue/database fault is isolated from the monitoring
            # scheduler job and will be retried on the next mail tick.
            logger.exception("account email worker failed")
            return
        if processed:
            logger.info("account email tick: processed %d job(s)", processed)

    async def _refresh_billing_access(self) -> None:
        async with self._db.session() as session:
            await expire_billing_entitlements(
                session,
                now=datetime.now(UTC),
                grace_days=self._settings.billing_past_due_grace_days,
            )
            await session.commit()

    @asynccontextmanager
    async def paused_for_maintenance(self) -> AsyncIterator[None]:
        """Pause future work and wait until both active jobs have drained.

        Both locks remain held for the whole maintenance window, preventing
        APScheduler and direct tick calls from touching the database while an
        administrator replaces it. The scheduler resumes even when maintenance
        raises.
        """
        was_running = self.running
        self._maintenance_paused = True
        try:
            if was_running:
                self._scheduler.pause()
            async with self._tick_lock, self._account_email_lock:
                yield
        finally:
            self._maintenance_paused = False
            if was_running and self.running:
                self._scheduler.resume()

    async def _check_due_sites(self) -> None:
        now = datetime.now(UTC)
        async with self._db.session() as session:
            await cancel_unrunnable_checks(session, now=now)
            due = await find_due_site_candidates(session, now)
            enqueued = await enqueue_scheduled_checks(
                session,
                due,
                now=now,
                limit=self._settings.max_checks_per_tick,
                global_capacity=self._settings.check_queue_capacity,
                per_org_capacity=self._settings.check_queue_per_org_capacity,
            )
            store = SettingsStore(session, SecretBox(*self._settings.encryption_keys))
            min_interval, jitter = await store.capture_pacing()
            retention = await store.snapshot_retention(default=self._settings.snapshot_retention)
            await session.commit()
        if enqueued:
            logger.info("tick: queued %d due site check(s)", len(enqueued))

        await self._drain_check_queue(
            limit=self._settings.max_checks_per_tick,
            min_interval=min_interval,
            jitter=jitter,
            retention=retention,
        )

    async def _drain_check_queue(
        self,
        *,
        limit: int,
        min_interval: float,
        jitter: float,
        retention: int,
    ) -> None:
        processed = 0
        while processed < limit:
            if processed:
                await _pace(min_interval, jitter)
            async with self._db.session() as session:
                job = await claim_next_check(
                    session,
                    now=datetime.now(UTC),
                    lease_seconds=self._effective_lease_seconds,
                    max_attempts=self._settings.check_job_max_attempts,
                )
            if job is None:
                return
            processed += 1
            await self._execute_job(job, retention=retention, propagate=False, bounded=True)

    async def run_manual_check(self, site_id: int, *, analyze: bool = True) -> RunResult:
        return await self._run_manual(site_id, kind=CheckJobKind.CHECK, analyze=analyze)

    async def run_manual_snapshot(self, site_id: int) -> RunResult:
        return await self._run_manual(site_id, kind=CheckJobKind.SNAPSHOT, analyze=False)

    async def _run_manual(self, site_id: int, *, kind: CheckJobKind, analyze: bool) -> RunResult:
        now = datetime.now(UTC)
        async with self._db.session() as session:
            job = await enqueue_and_claim_manual(
                session,
                site_id,
                kind=kind,
                analyze=analyze,
                now=now,
                lease_seconds=self._effective_lease_seconds,
                global_capacity=self._settings.check_queue_capacity,
                per_org_capacity=self._settings.check_queue_per_org_capacity,
            )
            await session.commit()
        result = await self._execute_job(
            job,
            retention=self._settings.snapshot_retention,
            propagate=True,
            bounded=False,
        )
        assert result is not None
        return result

    async def _execute_job(
        self,
        job: ClaimedCheckJob,
        *,
        retention: int,
        propagate: bool,
        bounded: bool,
    ) -> RunResult | None:
        try:
            operation = (
                self._runner.snapshot(job.site_id)
                if job.kind is CheckJobKind.SNAPSHOT
                else self._runner.run(job.site_id, analyze=job.analyze)
            )
            result = (
                await asyncio.wait_for(operation, timeout=self._settings.per_site_budget_seconds)
                if bounded
                else await operation
            )
        except asyncio.CancelledError:
            await self._record_job_failure(job, "check cancelled before completion")
            raise
        except TimeoutError:
            await self._record_job_failure(job, "site check exceeded its execution budget")
            logger.warning(
                "site %s job %s exceeded its %.0fs budget",
                job.site_id,
                job.id,
                self._settings.per_site_budget_seconds,
            )
            if propagate:
                raise
            return None
        except Exception as exc:
            await self._record_job_failure(job, _safe_job_error(exc))
            if propagate:
                raise
            logger.exception("queued check job %s failed for site %s", job.id, job.site_id)
            return None

        if result.capture_error:
            # Capture errors can contain a target URL, browser internals, or an
            # interaction value. The authorized caller still receives the
            # runner result, but the operations queue persists only a safe
            # category; detailed diagnostics remain in application logs.
            await self._record_job_failure(job, "CaptureError: capture failed")
            return result

        async with self._db.session() as session:
            completed = await complete_check(
                session,
                job,
                result=_result_payload(result),
                now=datetime.now(UTC),
            )
            if completed:
                await prune_site_history(session, job.site_id, keep=retention)
                await session.commit()
        return result

    async def _record_job_failure(self, job: ClaimedCheckJob, error: str) -> None:
        async with self._db.session() as session:
            await fail_check(
                session,
                job,
                error=error,
                now=datetime.now(UTC),
                max_attempts=self._settings.check_job_max_attempts,
            )

    @property
    def _effective_lease_seconds(self) -> int:
        return max(
            self._settings.check_job_lease_seconds,
            int(self._settings.per_site_budget_seconds) + 30,
        )

    async def _prune_old_usage(self) -> None:
        async with self._db.session() as session:
            await prune_ai_usage(session, older_than_days=self._settings.ai_usage_retention_days)
            await prune_check_jobs(
                session,
                older_than_days=self._settings.check_job_retention_days,
            )
            await prune_account_email_jobs(
                session,
                older_than_days=self._settings.account_email_job_retention_days,
            )
            await session.commit()

    async def _maybe_backup(self) -> None:
        """Rotated on-disk snapshots of the SQLite database, taken every
        ``backup_interval_hours`` into ``data_dir/backups``.

        Postgres deployments back up at the provider (see docs/DEPLOY.md), so
        this is a no-op there. The last-backup marker lives in memory but is
        seeded from the newest file on disk, so restarts neither lose the
        cadence nor trigger a spurious backup.
        """
        db_path = sqlite_file_path(self._settings.database_url)
        if db_path is None or not db_path.exists():
            return
        async with self._db.session() as session:
            store = SettingsStore(session, SecretBox(*self._settings.encryption_keys))
            interval_hours = await store.backup_interval_hours(
                default=self._settings.backup_interval_hours
            )
            keep = await store.backup_keep_count(default=self._settings.backup_keep_count)
        if interval_hours <= 0:
            return

        backups_dir = self._settings.data_dir / "backups"
        if self._last_backup_at is None:
            self._last_backup_at, self._last_backup_file = await to_thread.run_sync(
                _newest_backup, backups_dir, db_path.stem
            )
        now = datetime.now(UTC)
        if self._last_backup_at is not None and now - self._last_backup_at < timedelta(
            hours=interval_hours
        ):
            return

        dest = backups_dir / f"{db_path.stem}-{now.strftime('%Y%m%d-%H%M%S')}.db"
        await to_thread.run_sync(_run_backup, db_path, dest, keep)
        self._last_backup_at = now
        self._last_backup_file = dest.name
        logger.info("database backed up to %s", dest)

    async def _retry_pending_changes(self) -> None:
        async with self._db.session() as session:
            pending = await find_changes_to_retry(
                session, datetime.now(UTC), self._settings.max_checks_per_tick
            )
        if not pending:
            return
        logger.info("tick: retrying %d pending change(s)", len(pending))
        for change_id in pending:
            try:
                await self._runner.reprocess_change(change_id)
            except Exception:
                logger.exception("retry failed for change %s", change_id)


async def find_changes_to_retry(session: AsyncSession, now: datetime, limit: int) -> list[int]:
    # Bound the fetch in SQL: nulls-first/earliest-first ordering puts the most-due
    # rows first, so the top ``limit`` rows are the right candidates even during a
    # provider outage that leaves many changes in the error state. Due-time is
    # still checked in Python to avoid SQLite's naive-vs-aware datetime pitfalls.
    rows = (
        await session.execute(
            select(ChangeEvent.id, ChangeEvent.next_retry_at)
            .where(
                ChangeEvent.retry_status.is_(None),
                or_(ChangeEvent.ai_error.is_not(None), ChangeEvent.notification_error.is_not(None)),
            )
            .order_by(ChangeEvent.next_retry_at.asc().nulls_first(), ChangeEvent.id.asc())
            .limit(limit)
        )
    ).all()
    return [
        change_id
        for change_id, next_retry_at in rows
        if next_retry_at is None or _as_utc(next_retry_at) <= now
    ]


def _run_backup(db_path: Path, dest: Path, keep: int) -> None:
    """Snapshot the database and rotate old copies (runs in a worker thread)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    snapshot_sqlite(db_path, dest)
    # Timestamped names sort chronologically, so lexicographic order is age order.
    _prune_oldest(sorted(dest.parent.glob(f"{db_path.stem}-*.db")), keep)
    # Every restore drops a timestamped safety copy beside the live database and
    # nothing else ever deletes them — cap those with the same retention.
    _prune_oldest(sorted(db_path.parent.glob(f"{db_path.stem}-pre-restore-*.db")), keep)


def _prune_oldest(files: list[Path], keep: int) -> None:
    for stale in files[: max(len(files) - max(keep, 1), 0)]:
        stale.unlink(missing_ok=True)


def _newest_backup(directory: Path, stem: str) -> tuple[datetime | None, str | None]:
    """The mtime and name of the newest backup on disk, or ``(None, None)``."""
    candidates = sorted(directory.glob(f"{stem}-*.db")) if directory.exists() else []
    if not candidates:
        return None, None
    newest = candidates[-1]
    return datetime.fromtimestamp(newest.stat().st_mtime, tz=UTC), newest.name


async def _pace(min_interval: float, jitter: float) -> None:
    """Wait a polite, slightly randomised gap before the next capture."""
    delay = min_interval + (random.uniform(0, jitter) if jitter > 0 else 0.0)
    if delay > 0:
        await asyncio.sleep(delay)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def find_due_sites(session: AsyncSession, now: datetime) -> list[int]:
    return [candidate.site_id for candidate in await find_due_site_candidates(session, now)]


async def find_due_site_candidates(session: AsyncSession, now: datetime) -> list[DueSite]:
    rows = (
        await session.execute(
            select(
                Site.id,
                Site.organization_id,
                Site.last_checked_at,
                Site.check_interval_minutes,
            )
            .join(Organization, Organization.id == Site.organization_id)
            .where(Site.enabled, Organization.is_active.is_(True))
            .order_by(Site.last_checked_at.asc().nulls_first(), Site.id.asc())
        )
    ).all()
    due: list[DueSite] = []
    for site_id, organization_id, last_checked_at, interval_minutes in rows:
        if _is_due(last_checked_at, interval_minutes, now):
            due.append(
                DueSite(
                    site_id=site_id,
                    organization_id=organization_id,
                    last_checked_at=last_checked_at,
                )
            )
    return due


def _is_due(last_checked_at: datetime | None, interval_minutes: int, now: datetime) -> bool:
    if last_checked_at is None:
        return True
    return now - _as_utc(last_checked_at) >= timedelta(minutes=interval_minutes)


def _result_payload(result: RunResult) -> dict[str, object]:
    return {
        "site_id": result.site_id,
        "status": str(result.status),
        "change_id": result.change_id,
        "significant": result.significant,
        "notified": result.notified,
        "recipients": result.recipients,
        # Provider errors can include target URLs, request fragments, or
        # credentials. Durable operational state records only the category;
        # the detailed exception stays in the protected process logs.
        "ai_error": "AIError: analysis failed" if result.ai_error else None,
        "capture_error": None,
        "notification_mode": (
            str(result.notification_mode) if result.notification_mode is not None else None
        ),
    }


def _safe_job_error(exc: Exception) -> str:
    # Unexpected provider/browser exceptions may embed credentials or target
    # URLs. The detailed traceback stays in process logs; the durable queue gets
    # only a bounded error class suitable for an operations panel.
    return f"{type(exc).__name__}: check execution failed"
