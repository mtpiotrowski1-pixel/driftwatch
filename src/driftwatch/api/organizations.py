"""Organization (tenant) management — instance operator (superadmin) only.

An organization is an isolated workspace of projects, sites, and recipients.
The operator creates and manages them: to serve several clients from one
instance, or to let one client group multiple subsidiaries on their own
deployment. Members and org-admins live inside a single organization; only the
superadmin sees and administers them all.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from driftwatch.api.deps import (
    InstanceSuperadminUser,
    SessionDep,
    SettingsDep,
    StepUpUser,
    require_step_up,
)
from driftwatch.audit import record_audit_event
from driftwatch.billing.access import lock_organization_access
from driftwatch.models import AIUsage, Organization, Plan, Site, Subscription, User
from driftwatch.schemas import OrganizationCreate, OrganizationOut, OrganizationUpdate

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationOut])
async def list_organizations(
    session: SessionDep, _: InstanceSuperadminUser
) -> list[OrganizationOut]:
    orgs = list((await session.execute(select(Organization).order_by(Organization.name))).scalars())
    return await _serialize(session, orgs)


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    admin: InstanceSuperadminUser,
) -> OrganizationOut:
    await require_step_up(request, admin, settings)
    org = Organization(name=payload.name)
    session.add(org)
    await session.flush()
    record_audit_event(
        session,
        request,
        admin,
        action="organization.created",
        target_type="organization",
        target_id=org.id,
        target_label=org.name,
        organization_id=org.id,
    )
    return (await _serialize(session, [org]))[0]


@router.patch("/{org_id}", response_model=OrganizationOut)
async def update_organization(
    org_id: int,
    payload: OrganizationUpdate,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    admin: InstanceSuperadminUser,
) -> OrganizationOut:
    await _require_org(session, org_id)
    data = payload.model_dump(exclude_unset=True)
    entitlement_fields = {
        "is_active",
        "plan",
        "plan_id",
        "max_sites",
        "max_members",
        "monthly_ai_check_limit",
    }
    if data.keys() & entitlement_fields:
        await require_step_up(request, admin, settings)
    org = await _require_org(session, org_id, lock_access=True)
    if data.get("is_active") is True and org.billing_suspended_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Organization access is suspended by billing and can only be restored "
            "from a current provider subscription",
        )
    manual_entitlement_fields = entitlement_fields - {"is_active"}
    if data.keys() & manual_entitlement_fields:
        subscription_id = await session.scalar(
            select(Subscription.id).where(Subscription.organization_id == org.id).limit(1)
        )
        if subscription_id is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Organization entitlements are billing-managed and cannot be edited manually",
            )
    audited_fields = (
        "name",
        "is_active",
        "plan",
        "plan_id",
        "max_sites",
        "max_members",
        "monthly_ai_check_limit",
    )
    before = {field: getattr(org, field) for field in audited_fields}
    was_manually_suspended = org.manually_suspended_at is not None
    # Assigning a plan first copies its caps onto the org; any caps sent in the
    # same request are applied afterwards, so an explicit override still wins.
    if "plan_id" in data:
        await _apply_plan(session, org, data.pop("plan_id"))
    for key, value in data.items():
        setattr(org, key, value)
    if data.get("is_active") is False:
        org.manually_suspended_at = org.manually_suspended_at or datetime.now(UTC)
    elif data.get("is_active") is True:
        org.manually_suspended_at = None
    changes = {
        field: {"from": before[field], "to": getattr(org, field)}
        for field in audited_fields
        if before[field] != getattr(org, field)
    }
    is_manually_suspended = org.manually_suspended_at is not None
    if was_manually_suspended != is_manually_suspended:
        changes["manually_suspended"] = {
            "from": was_manually_suspended,
            "to": is_manually_suspended,
        }
    if changes:
        record_audit_event(
            session,
            request,
            admin,
            action="organization.updated",
            target_type="organization",
            target_id=org.id,
            target_label=org.name,
            organization_id=org.id,
            details={"changes": changes},
        )
    return (await _serialize(session, [org]))[0]


async def _apply_plan(session: AsyncSession, org: Organization, plan_id: int | None) -> None:
    if plan_id is None:
        org.plan_id = None
        return
    plan = await session.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Plan {plan_id} not found")
    org.plan_id = plan.id
    org.plan = plan.key
    org.max_sites = plan.max_sites
    org.max_members = plan.max_members
    org.monthly_ai_check_limit = plan.monthly_ai_check_limit


@router.delete("/{org_id}", status_code=status.HTTP_409_CONFLICT)
async def reject_organization_deletion(
    org_id: int,
    session: SessionDep,
    _admin: InstanceSuperadminUser,
    _step_up: StepUpUser,
) -> None:
    # Keep the legacy route as an explicit, fail-closed contract for API clients.
    # Billing and audit records are ledgers, not cascade-owned tenant data; a
    # destructive delete would either violate their RESTRICT keys or erase the
    # operational context needed for reconciliation and compliance.
    await _require_org(session, org_id)
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        "Permanent organization deletion is disabled; suspend the organization "
        "to preserve its billing and audit history",
    )


async def _require_org(
    session: AsyncSession,
    org_id: int,
    *,
    lock_access: bool = False,
) -> Organization:
    org = (
        await lock_organization_access(session, org_id)
        if lock_access
        else await session.get(Organization, org_id)
    )
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Organization {org_id} not found")
    return org


async def _serialize(session: AsyncSession, orgs: list[Organization]) -> list[OrganizationOut]:
    if not orgs:
        return []
    ids = [org.id for org in orgs]
    members = await _member_counts(session, ids)
    sites = await _counts(session, Site.organization_id, Site.id, ids)
    ai_checks = await _ai_checks_this_month(session, ids)
    billing_managed_ids = set(
        (
            await session.execute(
                select(Subscription.organization_id).where(Subscription.organization_id.in_(ids))
            )
        ).scalars()
    )
    result: list[OrganizationOut] = []
    for org in orgs:
        dto = OrganizationOut.model_validate(org)
        dto.member_count = members.get(org.id, 0)
        dto.site_count = sites.get(org.id, 0)
        dto.ai_checks_this_month = ai_checks.get(org.id, 0)
        dto.billing_managed = org.id in billing_managed_ids
        dto.billing_suspended = org.billing_suspended_at is not None
        result.append(dto)
    return result


async def _ai_checks_this_month(session: AsyncSession, ids: list[int]) -> dict[int, int]:
    """AI analysis calls billed to each org since the first of the current UTC
    month — the usage that the monthly AI limit is measured against."""
    now = datetime.now(UTC)
    month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    rows = await session.execute(
        select(AIUsage.organization_id, func.count(AIUsage.id))
        .where(AIUsage.organization_id.in_(ids), AIUsage.created_at >= month_start)
        .group_by(AIUsage.organization_id)
    )
    counts: dict[int, int] = {}
    for org_id, total in rows.all():
        counts[org_id] = total
    return counts


async def _member_counts(session: AsyncSession, ids: list[int]) -> dict[int, int]:
    rows = await session.execute(
        select(User.organization_id, func.count(User.id))
        .where(
            User.organization_id.in_(ids),
            User.is_superadmin.is_(False),
        )
        .group_by(User.organization_id)
    )
    counts: dict[int, int] = {}
    for organization_id, total in rows.all():
        if organization_id is not None:
            counts[organization_id] = total
    return counts


async def _counts(
    session: AsyncSession,
    group_col: InstrumentedAttribute[Any],
    count_col: InstrumentedAttribute[Any],
    ids: list[int],
) -> dict[int, int]:
    rows = await session.execute(
        select(group_col, func.count(count_col)).where(group_col.in_(ids)).group_by(group_col)
    )
    counts: dict[int, int] = {}
    for org_id, total in rows.all():
        counts[org_id] = total
    return counts
