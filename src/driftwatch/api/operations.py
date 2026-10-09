"""Authenticated platform telemetry for the instance operator."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from driftwatch import __version__
from driftwatch.api.deps import (
    DatabaseDep,
    ExplicitOrgContext,
    InstanceSuperadminUser,
    MaintenanceDep,
    SchedulerDep,
    SessionDep,
    SettingsDep,
    StepUpUser,
    SuperadminUser,
)
from driftwatch.api.health import _scheduler_is_stale, _storage_metrics
from driftwatch.audit import record_audit_event
from driftwatch.billing.service import BILLING_EVENT_PROCESSING_STALE_AFTER
from driftwatch.check_queue import (
    check_queue_metrics,
    redrive_dead_check,
    unresolved_dead_check_predicate,
)
from driftwatch.config import Settings
from driftwatch.enums import AccountEmailStatus, NotificationDeliveryStatus
from driftwatch.exceptions import NotFoundError
from driftwatch.models import (
    AccountEmailJob,
    BillingEventProcessing,
    NotificationDelivery,
    SiteCheckJob,
)
from driftwatch.monitoring.capture import CaptureError, PlaywrightCapturer
from driftwatch.monitoring.remote_capture import RemotePageCapturer
from driftwatch.schemas import (
    OperationsAccountEmailQueueOut,
    OperationsBillingWebhooksOut,
    OperationsCaptureOut,
    OperationsCheckQueueOut,
    OperationsDatabaseOut,
    OperationsDeadCheckIncidentOut,
    OperationsDeadCheckIncidentPage,
    OperationsDeadCheckRedriveOut,
    OperationsDeadCheckRedriveRequest,
    OperationsDeliveryQueueOut,
    OperationsMaintenanceOut,
    OperationsOverviewOut,
    OperationsSchedulerOut,
    OperationsStorageOut,
)

router = APIRouter(prefix="/api/operations", tags=["operations"])
logger = logging.getLogger(__name__)

_ACCOUNT_EMAIL_PENDING_STALE_AFTER = timedelta(minutes=5)
_ACCOUNT_EMAIL_FAILURE_RECENT_WINDOW = timedelta(hours=1)


@router.get("/overview", response_model=OperationsOverviewOut)
async def operations_overview(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    database: DatabaseDep,
    scheduler: SchedulerDep,
    maintenance: MaintenanceDep,
    _: InstanceSuperadminUser,
) -> OperationsOverviewOut:
    now = datetime.now(UTC)
    database_ok = True
    try:
        await database.ping()
    except Exception:
        database_ok = False
        logger.warning("operations database probe failed", exc_info=True)

    queue = await check_queue_metrics(session, now=now)
    deliveries = await _delivery_metrics(session, now)
    account_emails = await _account_email_metrics(session, now)
    billing_webhooks = await _billing_webhook_metrics(session, now)
    capture = await _capture_metrics(request)
    storage = _storage_metrics(settings)
    scheduler_stale = _scheduler_is_stale(scheduler, settings, now)
    scheduler_unavailable = scheduler.expected and (not scheduler.running or scheduler_stale)
    queue_at_capacity = queue.active >= settings.check_queue_capacity
    unsafe_public_capture = (
        not settings.is_local and capture.mode == "in_process" and capture.status != "ready"
    )
    degraded = (
        not database_ok
        or scheduler_unavailable
        or capture.status == "unavailable"
        or unsafe_public_capture
        or queue.dead > 0
        or queue_at_capacity
        or deliveries.failed > 0
        or account_emails.failed_recent > 0
        or account_emails.stale_pending
        or billing_webhooks.failed > 0
        or billing_webhooks.stale_processing > 0
        or _storage_is_low(settings, storage)
        or maintenance.enabled
    )
    return OperationsOverviewOut(
        generated_at=now,
        version=__version__,
        status="degraded" if degraded else "ok",
        database=OperationsDatabaseOut(
            backend="sqlite" if settings.database_url.startswith("sqlite") else "postgresql",
            reachable=database_ok,
        ),
        scheduler=OperationsSchedulerOut(
            expected=scheduler.expected,
            running=scheduler.running,
            stale=scheduler_stale,
            last_tick_at=scheduler.last_tick_at,
        ),
        capture=capture,
        check_queue=OperationsCheckQueueOut(
            pending=queue.pending,
            running=queue.running,
            dead=queue.dead,
            oldest_pending_seconds=queue.oldest_pending_seconds,
            capacity=settings.check_queue_capacity,
            at_capacity=queue_at_capacity,
        ),
        delivery_queue=deliveries,
        account_email_queue=account_emails,
        billing_webhooks=billing_webhooks,
        storage=OperationsStorageOut(
            **storage,
            last_backup_at=scheduler.last_backup_at,
            last_backup_file=scheduler.last_backup_file,
        ),
        maintenance=OperationsMaintenanceOut(
            enabled=maintenance.enabled,
            active_requests=maintenance.active_requests,
        ),
    )


@router.get("/check-jobs/dead", response_model=OperationsDeadCheckIncidentPage)
async def list_instance_dead_check_incidents(
    session: SessionDep,
    _: InstanceSuperadminUser,
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None, ge=1),
) -> OperationsDeadCheckIncidentPage:
    """List safe dead-job metadata across the instance control plane."""
    return await _dead_check_incident_page(
        session,
        organization_id=None,
        limit=limit,
        before_id=before_id,
    )


@router.get("/tenant/check-jobs/dead", response_model=OperationsDeadCheckIncidentPage)
async def list_tenant_dead_check_incidents(
    session: SessionDep,
    _: SuperadminUser,
    organization_id: ExplicitOrgContext,
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None, ge=1),
) -> OperationsDeadCheckIncidentPage:
    """List incidents only after the operator enters the authorized tenant."""
    return await _dead_check_incident_page(
        session,
        organization_id=organization_id,
        limit=limit,
        before_id=before_id,
    )


@router.get(
    "/tenant/check-jobs/dead/{job_id}",
    response_model=OperationsDeadCheckIncidentOut,
)
async def get_tenant_dead_check_incident(
    job_id: int,
    session: SessionDep,
    _: SuperadminUser,
    organization_id: ExplicitOrgContext,
) -> OperationsDeadCheckIncidentOut:
    job = await _tenant_dead_check(session, job_id, organization_id)
    return _dead_check_incident(job)


@router.post(
    "/tenant/check-jobs/dead/{job_id}/redrive",
    response_model=OperationsDeadCheckRedriveOut,
)
async def redrive_tenant_dead_check_incident(
    job_id: int,
    payload: OperationsDeadCheckRedriveRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    admin: SuperadminUser,
    _: StepUpUser,
    organization_id: ExplicitOrgContext,
) -> OperationsDeadCheckRedriveOut:
    job, created = await redrive_dead_check(
        session,
        job_id,
        organization_id=organization_id,
        request_key=payload.idempotency_key,
        request_sha256=_redrive_request_sha256(payload),
        now=datetime.now(UTC),
        global_capacity=settings.check_queue_capacity,
        per_org_capacity=settings.check_queue_per_org_capacity,
    )
    if created:
        record_audit_event(
            session,
            request,
            admin,
            action="check_job.redriven",
            target_type="site_check_job",
            target_id=job.id,
            organization_id=organization_id,
            details={
                "original_job_id": job_id,
                "new_job_id": job.id,
                "site_id": job.site_id,
                "reason": payload.reason,
                "ticket": payload.ticket,
            },
        )
    return OperationsDeadCheckRedriveOut(
        created=created,
        job=_dead_check_incident(job),
    )


async def _dead_check_incident_page(
    session: SessionDep,
    *,
    organization_id: int | None,
    limit: int,
    before_id: int | None,
) -> OperationsDeadCheckIncidentPage:
    statement = select(SiteCheckJob).where(unresolved_dead_check_predicate())
    if organization_id is not None:
        statement = statement.where(SiteCheckJob.organization_id == organization_id)
    if before_id is not None:
        statement = statement.where(SiteCheckJob.id < before_id)
    rows = list(
        (
            await session.execute(statement.order_by(SiteCheckJob.id.desc()).limit(limit + 1))
        ).scalars()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return OperationsDeadCheckIncidentPage(
        items=[_dead_check_incident(job) for job in page],
        next_before_id=page[-1].id if has_more else None,
    )


async def _tenant_dead_check(
    session: SessionDep,
    job_id: int,
    organization_id: int,
) -> SiteCheckJob:
    job = await session.scalar(
        select(SiteCheckJob).where(
            SiteCheckJob.id == job_id,
            SiteCheckJob.organization_id == organization_id,
            unresolved_dead_check_predicate(),
        )
    )
    if job is None:
        raise NotFoundError("Dead check incident not found")
    return job


def _dead_check_incident(job: SiteCheckJob) -> OperationsDeadCheckIncidentOut:
    return OperationsDeadCheckIncidentOut(
        id=job.id,
        organization_id=job.organization_id,
        site_id=job.site_id,
        original_job_id=job.original_job_id,
        kind=job.kind,
        source=job.source,
        status=job.status,
        analyze=job.analyze,
        attempt_count=job.attempt_count,
        enqueued_at=job.enqueued_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _redrive_request_sha256(payload: OperationsDeadCheckRedriveRequest) -> str:
    canonical = json.dumps(
        {"reason": payload.reason, "ticket": payload.ticket},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


async def _billing_webhook_metrics(
    session: SessionDep,
    now: datetime,
) -> OperationsBillingWebhooksOut:
    stale_before = now - BILLING_EVENT_PROCESSING_STALE_AFTER
    row = (
        await session.execute(
            select(
                func.count(BillingEventProcessing.billing_event_id),
                func.count(BillingEventProcessing.billing_event_id).filter(
                    BillingEventProcessing.status == "received"
                ),
                func.count(BillingEventProcessing.billing_event_id).filter(
                    BillingEventProcessing.status == "processing"
                ),
                func.count(BillingEventProcessing.billing_event_id).filter(
                    BillingEventProcessing.status == "processing",
                    BillingEventProcessing.updated_at < stale_before,
                ),
                func.count(BillingEventProcessing.billing_event_id).filter(
                    BillingEventProcessing.processed_at.is_not(None)
                ),
                func.count(BillingEventProcessing.billing_event_id).filter(
                    BillingEventProcessing.status == "failed"
                ),
                func.max(BillingEventProcessing.processed_at),
                func.max(BillingEventProcessing.updated_at).filter(
                    BillingEventProcessing.status == "failed"
                ),
            )
        )
    ).one()
    return OperationsBillingWebhooksOut(
        total=int(row[0] or 0),
        received=int(row[1] or 0),
        processing=int(row[2] or 0),
        stale_processing=int(row[3] or 0),
        completed=int(row[4] or 0),
        failed=int(row[5] or 0),
        stale_after_seconds=int(BILLING_EVENT_PROCESSING_STALE_AFTER.total_seconds()),
        last_processed_at=_as_utc(row[6]),
        last_failed_at=_as_utc(row[7]),
    )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _storage_is_low(settings: Settings, storage: dict[str, int | None]) -> bool:
    """Keep enough SQLite headroom for a safety copy and database replacement."""
    if not settings.database_url.startswith("sqlite"):
        return False
    free = storage["disk_free_bytes"]
    if free is None:
        return True
    database_bytes = storage["db_bytes"] or 0
    required = max(512 * 1024 * 1024, database_bytes * 2)
    return free < required


async def _capture_metrics(request: Request) -> OperationsCaptureOut:
    capturer = getattr(request.app.state, "page_capturer", None)
    if isinstance(capturer, RemotePageCapturer):
        try:
            probe = await capturer.probe()
        except CaptureError:
            logger.warning("capture worker readiness probe failed", exc_info=True)
            return OperationsCaptureOut(mode="isolated_worker", status="unavailable")
        return OperationsCaptureOut(
            mode="isolated_worker",
            status="ready",
            active=probe.active,
            queued=probe.queued,
            active_capacity=probe.active_capacity,
            queue_capacity=probe.queue_capacity,
        )
    # Dependency-injected capturers are used by tests and bespoke self-hosted
    # integrations. Neither they nor in-process Playwright expose a cheap health
    # probe, so report the honest unknown state rather than a fabricated green.
    mode = "in_process" if isinstance(capturer, PlaywrightCapturer) else "injected"
    return OperationsCaptureOut(mode=mode, status="not_probed")


async def _delivery_metrics(session: SessionDep, now: datetime) -> OperationsDeliveryQueueOut:
    grouped = (
        await session.execute(
            select(NotificationDelivery.status, func.count(NotificationDelivery.id)).group_by(
                NotificationDelivery.status
            )
        )
    ).all()
    counts = {
        NotificationDeliveryStatus(delivery_status): int(count)
        for delivery_status, count in grouped
    }
    exhausted = int(
        await session.scalar(
            select(func.count(NotificationDelivery.id)).where(
                NotificationDelivery.status == NotificationDeliveryStatus.FAILED,
                NotificationDelivery.next_attempt_at.is_(None),
                NotificationDelivery.lease_token.is_(None),
            )
        )
        or 0
    )
    leased = int(
        await session.scalar(
            select(func.count(NotificationDelivery.id)).where(
                NotificationDelivery.lease_token.is_not(None)
            )
        )
        or 0
    )
    oldest = await session.scalar(
        select(func.min(NotificationDelivery.created_at)).where(
            NotificationDelivery.status != NotificationDeliveryStatus.SENT
        )
    )
    oldest_age = None
    if oldest is not None:
        oldest_utc = oldest if oldest.tzinfo is not None else oldest.replace(tzinfo=UTC)
        oldest_age = max(0.0, (now - oldest_utc).total_seconds())
    return OperationsDeliveryQueueOut(
        pending=counts.get(NotificationDeliveryStatus.PENDING, 0),
        failed=counts.get(NotificationDeliveryStatus.FAILED, 0),
        sent=counts.get(NotificationDeliveryStatus.SENT, 0),
        exhausted=exhausted,
        leased=leased,
        oldest_unsent_seconds=oldest_age,
    )


async def _account_email_metrics(
    session: SessionDep,
    now: datetime,
) -> OperationsAccountEmailQueueOut:
    grouped = (
        await session.execute(
            select(AccountEmailJob.status, func.count(AccountEmailJob.id)).group_by(
                AccountEmailJob.status
            )
        )
    ).all()
    counts = {AccountEmailStatus(job_status): int(count) for job_status, count in grouped}
    failure_cutoff = now - _ACCOUNT_EMAIL_FAILURE_RECENT_WINDOW
    failed_recent = int(
        await session.scalar(
            select(func.count(AccountEmailJob.id)).where(
                AccountEmailJob.status == AccountEmailStatus.FAILED,
                AccountEmailJob.finished_at.is_not(None),
                AccountEmailJob.finished_at >= failure_cutoff,
            )
        )
        or 0
    )
    leased = int(
        await session.scalar(
            select(func.count(AccountEmailJob.id)).where(
                AccountEmailJob.status == AccountEmailStatus.PENDING,
                AccountEmailJob.lease_token.is_not(None),
                AccountEmailJob.lease_expires_at > now,
            )
        )
        or 0
    )
    oldest = await session.scalar(
        select(func.min(AccountEmailJob.scheduled_at)).where(
            AccountEmailJob.status == AccountEmailStatus.PENDING
        )
    )
    oldest_age = None
    if oldest is not None:
        oldest_utc = oldest if oldest.tzinfo is not None else oldest.replace(tzinfo=UTC)
        oldest_age = max(0.0, (now - oldest_utc).total_seconds())
    stale_after_seconds = int(_ACCOUNT_EMAIL_PENDING_STALE_AFTER.total_seconds())
    return OperationsAccountEmailQueueOut(
        pending=counts.get(AccountEmailStatus.PENDING, 0),
        failed_total=counts.get(AccountEmailStatus.FAILED, 0),
        failed_recent=failed_recent,
        sent=counts.get(AccountEmailStatus.SENT, 0),
        cancelled=counts.get(AccountEmailStatus.CANCELLED, 0),
        leased=leased,
        oldest_pending_seconds=oldest_age,
        stale_pending=oldest_age is not None and oldest_age > stale_after_seconds,
        pending_stale_after_seconds=stale_after_seconds,
        recent_failure_window_seconds=int(_ACCOUNT_EMAIL_FAILURE_RECENT_WINDOW.total_seconds()),
    )
