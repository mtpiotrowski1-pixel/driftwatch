"""Scoped read access to the append-only administrative audit trail."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from driftwatch.api.deps import AdminUser, SessionDep
from driftwatch.models import AuditEvent
from driftwatch.schemas import AuditEventOut

router = APIRouter(prefix="/api/audit-events", tags=["audit"])


@router.get("", response_model=list[AuditEventOut])
async def list_audit_events(
    session: SessionDep,
    _: AdminUser,
    limit: int = Query(default=100, ge=1, le=200),
    before_id: int | None = Query(default=None, ge=1),
) -> list[AuditEvent]:
    """Return newest events visible in the current tenant context.

    Instance scope contains only control-plane events. Tenant admins and an
    operator who entered a tenant see only that organization's events. This
    keeps tenant labels, identities, and change metadata behind the same
    support-access boundary as the tenant resources they describe.
    """
    statement = select(AuditEvent)
    info = session.sync_session.info
    if info.get("org_superadmin"):
        statement = statement.where(AuditEvent.organization_id.is_(None))
    else:
        statement = statement.where(AuditEvent.organization_id == info.get("org_id"))
    if before_id is not None:
        statement = statement.where(AuditEvent.id < before_id)
    rows = await session.execute(statement.order_by(AuditEvent.id.desc()).limit(limit))
    return list(rows.scalars())
