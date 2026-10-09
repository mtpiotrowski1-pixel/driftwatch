"""Durable, tenant-fair queue for scheduled and manual site captures.

The database is the source of truth. Enqueue capacity is serialized by a
singleton lock row, active work is unique per site, and claims carry expiring
leases so another replica can recover work after a process crash.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast
from uuid import uuid4

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from driftwatch.enums import CheckJobKind, CheckJobSource, CheckJobStatus
from driftwatch.exceptions import AccessDenied, ConflictError, NotFoundError
from driftwatch.models import CheckQueueState, Organization, Site, SiteCheckJob

_ACTIVE_STATUSES = (CheckJobStatus.PENDING, CheckJobStatus.RUNNING)
_RETRY_BACKOFF_SECONDS: tuple[int, ...] = (60, 300, 900, 3_600)


class SiteCheckBusy(ConflictError):
    """A queued or leased job already owns this site."""


class CheckQueueFull(ConflictError):
    """Global or tenant queue backpressure rejected new work."""


@dataclass(frozen=True, slots=True)
class DueSite:
    site_id: int
    organization_id: int
    last_checked_at: datetime | None


@dataclass(frozen=True, slots=True)
class ClaimedCheckJob:
    id: int
    organization_id: int
    site_id: int
    kind: CheckJobKind
    source: CheckJobSource
    analyze: bool
    attempt_count: int
    lease_token: str


@dataclass(frozen=True, slots=True)
class CheckQueueMetrics:
    pending: int
    running: int
    dead: int
    oldest_pending_seconds: float | None

    @property
    def active(self) -> int:
        return self.pending + self.running


async def enqueue_scheduled_checks(
    session: AsyncSession,
    candidates: list[DueSite],
    *,
    now: datetime,
    limit: int,
    global_capacity: int,
    per_org_capacity: int,
) -> list[int]:
    """Enqueue due sites round-robin by tenant under hard queue caps."""
    if not candidates or limit <= 0:
        return []
    await _lock_capacity(session, now)
    global_active, active_by_org, active_sites = await _active_counts(session)
    room = max(global_capacity - global_active, 0)
    if room == 0:
        return []

    ordered = _round_robin(candidates)
    known_keys = await _known_idempotency_keys(
        session, [candidate.site_id for candidate in ordered]
    )
    inserted: list[SiteCheckJob] = []
    for candidate in ordered:
        if len(inserted) >= min(limit, room):
            break
        if candidate.site_id in active_sites:
            continue
        if active_by_org[candidate.organization_id] >= per_org_capacity:
            continue
        key = _scheduled_key(candidate)
        if key in known_keys:
            continue
        job = SiteCheckJob(
            organization_id=candidate.organization_id,
            site_id=candidate.site_id,
            idempotency_key=key,
            kind=CheckJobKind.CHECK,
            source=CheckJobSource.SCHEDULED,
            analyze=True,
            status=CheckJobStatus.PENDING,
            attempt_count=0,
            available_at=now,
            enqueued_at=now,
        )
        session.add(job)
        inserted.append(job)
        known_keys.add(key)
        active_sites.add(candidate.site_id)
        active_by_org[candidate.organization_id] += 1
    await session.flush()
    return [job.id for job in inserted]


async def enqueue_and_claim_manual(
    session: AsyncSession,
    site_id: int,
    *,
    kind: CheckJobKind,
    analyze: bool,
    now: datetime,
    lease_seconds: int,
    global_capacity: int,
    per_org_capacity: int,
) -> ClaimedCheckJob:
    """Reserve a site's active slot and lease it to the calling HTTP request."""
    await _lock_capacity(session, now)
    site = await session.get(Site, site_id)
    if site is None:
        raise NotFoundError(f"site {site_id} not found")
    organization = await session.get(Organization, site.organization_id)
    if organization is None or not organization.is_active:
        raise AccessDenied("This organization is suspended or no longer exists")

    active = (
        await session.execute(
            select(SiteCheckJob.id).where(
                SiteCheckJob.site_id == site_id,
                SiteCheckJob.status.in_(_ACTIVE_STATUSES),
            )
        )
    ).first()
    if active is not None:
        raise SiteCheckBusy("A check for this site is already queued or running")

    global_active, active_by_org, _ = await _active_counts(session)
    if global_active >= global_capacity:
        raise CheckQueueFull("The check queue is at capacity; try again later")
    if active_by_org[site.organization_id] >= per_org_capacity:
        raise CheckQueueFull("This workspace has reached its queued-check limit")

    token = str(uuid4())
    job = SiteCheckJob(
        organization_id=site.organization_id,
        site_id=site.id,
        idempotency_key=f"manual:{site.id}:{uuid4()}",
        kind=kind,
        source=CheckJobSource.MANUAL,
        analyze=analyze,
        status=CheckJobStatus.RUNNING,
        attempt_count=1,
        available_at=None,
        lease_token=token,
        lease_expires_at=now + timedelta(seconds=lease_seconds),
        enqueued_at=now,
        started_at=now,
    )
    session.add(job)
    organization.check_queue_claimed_at = now
    try:
        await session.flush()
    except IntegrityError as exc:
        raise SiteCheckBusy("A check for this site is already queued or running") from exc
    return _claimed(job, token)


async def redrive_dead_check(
    session: AsyncSession,
    dead_job_id: int,
    *,
    organization_id: int,
    request_key: str,
    request_sha256: str,
    now: datetime,
    global_capacity: int,
    per_org_capacity: int,
) -> tuple[SiteCheckJob, bool]:
    """Create one pending recovery generation for a terminal check job.

    The queue-capacity lock serializes this reservation with scheduled and
    manual work across replicas. The original terminal row stays immutable;
    repeating the same request returns its previously created child.
    """
    if re.fullmatch(r"[0-9a-f]{64}", request_sha256) is None:
        raise ValueError("request_sha256 must be a hexadecimal SHA-256 digest")

    idempotency_key = _redrive_key(dead_job_id, request_key)
    await _lock_capacity(session, now)
    original = await session.scalar(
        select(SiteCheckJob)
        .where(
            SiteCheckJob.id == dead_job_id,
            SiteCheckJob.organization_id == organization_id,
        )
        .with_for_update()
    )
    if original is None:
        raise NotFoundError("Dead check incident not found")
    if original.status != CheckJobStatus.DEAD:
        raise ConflictError("Only a dead check job can be redriven")

    existing = await _redrive_by_key(
        session,
        idempotency_key=idempotency_key,
        original_job_id=original.id,
        organization_id=organization_id,
    )
    if existing is not None:
        if existing.redrive_request_sha256 != request_sha256:
            raise ConflictError("The idempotency key was already used with another request")
        return existing, False

    existing_child_id = await session.scalar(
        select(SiteCheckJob.id).where(SiteCheckJob.original_job_id == original.id).limit(1)
    )
    if existing_child_id is not None:
        raise ConflictError("This dead check incident has already been redriven")

    organization = await session.scalar(
        select(Organization).where(Organization.id == organization_id).with_for_update()
    )
    if organization is None or not organization.is_active:
        raise ConflictError("The organization must be active before redriving a check")
    site = await session.scalar(
        select(Site)
        .where(
            Site.id == original.site_id,
            Site.organization_id == organization_id,
        )
        .with_for_update()
    )
    if site is None:
        raise NotFoundError("The incident site no longer exists")
    if not site.enabled:
        raise ConflictError("The site must be enabled before redriving a check")

    global_active, active_by_org, active_sites = await _active_counts(session)
    if site.id in active_sites:
        raise SiteCheckBusy("A check for this site is already queued or running")
    if global_active >= global_capacity:
        raise CheckQueueFull("The check queue is at capacity; try again later")
    if active_by_org[organization_id] >= per_org_capacity:
        raise CheckQueueFull("This workspace has reached its queued-check limit")

    job = SiteCheckJob(
        organization_id=organization_id,
        site_id=site.id,
        original_job_id=original.id,
        redrive_request_sha256=request_sha256,
        idempotency_key=idempotency_key,
        kind=original.kind,
        source=CheckJobSource.REDRIVE,
        analyze=original.analyze,
        status=CheckJobStatus.PENDING,
        attempt_count=0,
        available_at=now,
        enqueued_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(job)
            await session.flush()
    except IntegrityError as exc:
        existing = await _redrive_by_key(
            session,
            idempotency_key=idempotency_key,
            original_job_id=original.id,
            organization_id=organization_id,
        )
        if existing is not None:
            if existing.redrive_request_sha256 != request_sha256:
                raise ConflictError(
                    "The idempotency key was already used with another request"
                ) from exc
            return existing, False
        existing_child_id = await session.scalar(
            select(SiteCheckJob.id).where(SiteCheckJob.original_job_id == original.id).limit(1)
        )
        if existing_child_id is not None:
            raise ConflictError("This dead check incident has already been redriven") from exc
        raise SiteCheckBusy("A check for this site is already queued or running") from exc
    return job, True


async def claim_next_check(
    session: AsyncSession,
    *,
    now: datetime,
    lease_seconds: int,
    max_attempts: int = 5,
) -> ClaimedCheckJob | None:
    """Claim due work, including crash recovery, within the attempt budget."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    # A process can disappear before fail_check runs. Expiring a final lease
    # therefore has to be a terminal transition here, not a sixth attempt.
    await session.execute(
        update(SiteCheckJob)
        .where(_claimable(now), SiteCheckJob.attempt_count >= max_attempts)
        .values(
            status=CheckJobStatus.DEAD,
            available_at=None,
            lease_token=None,
            lease_expires_at=None,
            completed_at=now,
            last_error="check attempt budget exhausted before reclaim",
        )
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    claimable = _claimable(now)
    for _ in range(3):
        candidate = (
            await session.execute(
                select(SiteCheckJob)
                .join(Organization, Organization.id == SiteCheckJob.organization_id)
                .join(Site, Site.id == SiteCheckJob.site_id)
                .where(
                    claimable,
                    SiteCheckJob.attempt_count < max_attempts,
                    Organization.is_active.is_(True),
                    or_(
                        SiteCheckJob.source == CheckJobSource.MANUAL,
                        Site.enabled.is_(True),
                    ),
                )
                .order_by(
                    Organization.check_queue_claimed_at.asc().nulls_first(),
                    SiteCheckJob.available_at.asc().nulls_first(),
                    SiteCheckJob.enqueued_at.asc(),
                    SiteCheckJob.id.asc(),
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()
        if candidate is None:
            await session.rollback()
            return None

        token = str(uuid4())
        row = (
            await session.execute(
                update(SiteCheckJob)
                .where(
                    SiteCheckJob.id == candidate.id,
                    _claimable(now),
                    SiteCheckJob.attempt_count < max_attempts,
                )
                .values(
                    status=CheckJobStatus.RUNNING,
                    attempt_count=SiteCheckJob.attempt_count + 1,
                    available_at=None,
                    lease_token=token,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                    started_at=now,
                )
                .execution_options(synchronize_session=False)
                .returning(
                    SiteCheckJob.id,
                    SiteCheckJob.organization_id,
                    SiteCheckJob.site_id,
                    SiteCheckJob.kind,
                    SiteCheckJob.source,
                    SiteCheckJob.analyze,
                    SiteCheckJob.attempt_count,
                )
            )
        ).one_or_none()
        if row is None:
            await session.rollback()
            continue
        await session.execute(
            update(Organization)
            .where(Organization.id == row.organization_id)
            .values(check_queue_claimed_at=now)
        )
        await session.commit()
        return ClaimedCheckJob(
            id=row.id,
            organization_id=row.organization_id,
            site_id=row.site_id,
            kind=CheckJobKind(row.kind),
            source=CheckJobSource(row.source),
            analyze=row.analyze,
            attempt_count=row.attempt_count,
            lease_token=token,
        )
    return None


async def complete_check(
    session: AsyncSession,
    job: ClaimedCheckJob,
    *,
    result: dict[str, object],
    now: datetime,
) -> bool:
    completed = (
        await session.execute(
            update(SiteCheckJob)
            .where(
                SiteCheckJob.id == job.id,
                SiteCheckJob.status == CheckJobStatus.RUNNING,
                SiteCheckJob.lease_token == job.lease_token,
            )
            .values(
                status=CheckJobStatus.SUCCEEDED,
                lease_token=None,
                lease_expires_at=None,
                completed_at=now,
                last_error=None,
                result=result,
            )
            .execution_options(synchronize_session=False)
            .returning(SiteCheckJob.id)
        )
    ).scalar_one_or_none()
    await session.commit()
    return completed is not None


async def fail_check(
    session: AsyncSession,
    job: ClaimedCheckJob,
    *,
    error: str,
    now: datetime,
    max_attempts: int,
) -> CheckJobStatus | None:
    exhausted = job.attempt_count >= max_attempts
    status = CheckJobStatus.DEAD if exhausted else CheckJobStatus.PENDING
    available_at = None if exhausted else now + _retry_delay(job.attempt_count)
    failed = (
        await session.execute(
            update(SiteCheckJob)
            .where(
                SiteCheckJob.id == job.id,
                SiteCheckJob.status == CheckJobStatus.RUNNING,
                SiteCheckJob.lease_token == job.lease_token,
            )
            .values(
                status=status,
                available_at=available_at,
                lease_token=None,
                lease_expires_at=None,
                completed_at=now if exhausted else None,
                last_error=_bounded_error(error),
            )
            .execution_options(synchronize_session=False)
            .returning(SiteCheckJob.id)
        )
    ).scalar_one_or_none()
    await session.commit()
    return status if failed is not None else None


async def cancel_unrunnable_checks(session: AsyncSession, *, now: datetime) -> int:
    reclaimable = or_(
        SiteCheckJob.status == CheckJobStatus.PENDING,
        (
            (SiteCheckJob.status == CheckJobStatus.RUNNING)
            & (SiteCheckJob.lease_expires_at.is_not(None))
            & (SiteCheckJob.lease_expires_at <= now)
        ),
    )
    ineligible = (
        select(SiteCheckJob.id)
        .join(Site, Site.id == SiteCheckJob.site_id)
        .join(Organization, Organization.id == SiteCheckJob.organization_id)
        .where(
            reclaimable,
            or_(
                Organization.is_active.is_(False),
                ((SiteCheckJob.source != CheckJobSource.MANUAL) & Site.enabled.is_(False)),
            ),
        )
    )
    result = cast(
        CursorResult[object],
        await session.execute(
            update(SiteCheckJob)
            .where(SiteCheckJob.id.in_(ineligible))
            .values(
                status=CheckJobStatus.CANCELLED,
                available_at=None,
                lease_token=None,
                lease_expires_at=None,
                completed_at=now,
                last_error="site disabled or organization suspended",
            )
            .execution_options(synchronize_session=False)
        ),
    )
    return result.rowcount or 0


async def check_queue_metrics(
    session: AsyncSession, *, now: datetime | None = None
) -> CheckQueueMetrics:
    rows = (
        await session.execute(
            select(SiteCheckJob.status, func.count(SiteCheckJob.id))
            .where(
                or_(
                    SiteCheckJob.status != CheckJobStatus.DEAD,
                    unresolved_dead_check_predicate(),
                )
            )
            .group_by(SiteCheckJob.status)
        )
    ).all()
    counts: dict[CheckJobStatus, int] = {
        CheckJobStatus(status): int(count) for status, count in rows
    }
    oldest = (
        await session.execute(
            select(func.min(SiteCheckJob.enqueued_at)).where(
                SiteCheckJob.status == CheckJobStatus.PENDING
            )
        )
    ).scalar_one()
    age = None
    if oldest is not None:
        age = max(0.0, ((now or datetime.now(UTC)) - _as_utc(oldest)).total_seconds())
    return CheckQueueMetrics(
        pending=int(counts.get(CheckJobStatus.PENDING, 0)),
        running=int(counts.get(CheckJobStatus.RUNNING, 0)),
        dead=int(counts.get(CheckJobStatus.DEAD, 0)),
        oldest_pending_seconds=age,
    )


async def prune_check_jobs(
    session: AsyncSession, *, older_than_days: int, now: datetime | None = None
) -> int:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=older_than_days)
    result = cast(
        CursorResult[object],
        await session.execute(
            delete(SiteCheckJob).where(
                SiteCheckJob.status.in_(
                    (
                        CheckJobStatus.SUCCEEDED,
                        CheckJobStatus.DEAD,
                        CheckJobStatus.CANCELLED,
                    )
                ),
                SiteCheckJob.completed_at < cutoff,
            )
        ),
    )
    return result.rowcount or 0


async def _lock_capacity(session: AsyncSession, now: datetime) -> None:
    locked = (
        await session.execute(
            update(CheckQueueState)
            .where(CheckQueueState.id == 1)
            .values(updated_at=now)
            .returning(CheckQueueState.id)
        )
    ).scalar_one_or_none()
    if locked is not None:
        return
    try:
        async with session.begin_nested():
            session.add(CheckQueueState(id=1, updated_at=now))
            await session.flush()
    except IntegrityError:
        pass
    locked = (
        await session.execute(
            update(CheckQueueState)
            .where(CheckQueueState.id == 1)
            .values(updated_at=now)
            .returning(CheckQueueState.id)
        )
    ).scalar_one_or_none()
    if locked is None:
        raise RuntimeError("Unable to acquire the check queue capacity lock")


async def _active_counts(
    session: AsyncSession,
) -> tuple[int, defaultdict[int, int], set[int]]:
    rows = (
        await session.execute(
            select(
                SiteCheckJob.organization_id,
                SiteCheckJob.site_id,
            ).where(SiteCheckJob.status.in_(_ACTIVE_STATUSES))
        )
    ).all()
    by_org: defaultdict[int, int] = defaultdict(int)
    sites: set[int] = set()
    for organization_id, site_id in rows:
        by_org[organization_id] += 1
        sites.add(site_id)
    return len(rows), by_org, sites


async def _known_idempotency_keys(session: AsyncSession, site_ids: list[int]) -> set[str]:
    if not site_ids:
        return set()
    keys: set[str] = set()
    for start in range(0, len(site_ids), 500):
        chunk = site_ids[start : start + 500]
        keys.update(
            (
                await session.execute(
                    select(SiteCheckJob.idempotency_key).where(SiteCheckJob.site_id.in_(chunk))
                )
            ).scalars()
        )
    return keys


async def _redrive_by_key(
    session: AsyncSession,
    *,
    idempotency_key: str,
    original_job_id: int,
    organization_id: int,
) -> SiteCheckJob | None:
    return cast(
        SiteCheckJob | None,
        await session.scalar(
            select(SiteCheckJob).where(
                SiteCheckJob.idempotency_key == idempotency_key,
                SiteCheckJob.original_job_id == original_job_id,
                SiteCheckJob.organization_id == organization_id,
            )
        ),
    )


def _round_robin(candidates: list[DueSite]) -> list[DueSite]:
    queues: dict[int, deque[DueSite]] = defaultdict(deque)
    tenant_order: list[int] = []
    for candidate in candidates:
        if candidate.organization_id not in queues:
            tenant_order.append(candidate.organization_id)
        queues[candidate.organization_id].append(candidate)
    ordered: list[DueSite] = []
    while queues:
        for organization_id in list(tenant_order):
            queue = queues.get(organization_id)
            if not queue:
                tenant_order.remove(organization_id)
                queues.pop(organization_id, None)
                continue
            ordered.append(queue.popleft())
    return ordered


def _claimable(now: datetime) -> ColumnElement[bool]:
    return or_(
        (
            (SiteCheckJob.status == CheckJobStatus.PENDING)
            & (SiteCheckJob.available_at.is_not(None))
            & (SiteCheckJob.available_at <= now)
        ),
        (
            (SiteCheckJob.status == CheckJobStatus.RUNNING)
            & (SiteCheckJob.lease_expires_at.is_not(None))
            & (SiteCheckJob.lease_expires_at <= now)
        ),
    )


def _scheduled_key(candidate: DueSite) -> str:
    marker = (
        _as_utc(candidate.last_checked_at).isoformat(timespec="microseconds")
        if candidate.last_checked_at is not None
        else "never"
    )
    return f"scheduled:{candidate.site_id}:{marker}"


def _redrive_key(dead_job_id: int, request_key: str) -> str:
    request_key_sha256 = sha256(request_key.encode("utf-8")).hexdigest()
    return f"redrive:{dead_job_id}:{request_key_sha256}"


def unresolved_dead_check_predicate() -> ColumnElement[bool]:
    """Select dead jobs that have not yet produced a recovery generation."""
    child = aliased(SiteCheckJob)
    return (SiteCheckJob.status == CheckJobStatus.DEAD) & ~exists(
        select(child.id).where(child.original_job_id == SiteCheckJob.id)
    )


def _retry_delay(attempt: int) -> timedelta:
    index = min(max(attempt - 1, 0), len(_RETRY_BACKOFF_SECONDS) - 1)
    return timedelta(seconds=_RETRY_BACKOFF_SECONDS[index])


def _bounded_error(error: str) -> str:
    normalized = " ".join(error.split()) or "check execution failed"
    return normalized[:500]


def _claimed(job: SiteCheckJob, token: str) -> ClaimedCheckJob:
    return ClaimedCheckJob(
        id=job.id,
        organization_id=job.organization_id,
        site_id=job.site_id,
        kind=CheckJobKind(job.kind),
        source=CheckJobSource(job.source),
        analyze=job.analyze,
        attempt_count=job.attempt_count,
        lease_token=token,
    )


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
