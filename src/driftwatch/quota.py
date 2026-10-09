"""Transactional tenant quotas for monitored sites and AI analyses.

Reservations are database updates, not ``count()`` followed by an insert. The
organization row is therefore the serialization point on Postgres and SQLite:
concurrent requests cannot both observe the last free slot. Counters are
reconciled with the underlying rows on every reservation so legacy/manual data
cannot make enforcement under-count.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.exceptions import AccessDenied, PlanLimitReached
from driftwatch.models import AIUsage, Organization, Site, User

_SITE_LIMIT_MESSAGE = (
    "This workspace allows {limit} monitored site(s). Contact an operator to request more access."
)
_MEMBER_LIMIT_MESSAGE = (
    "This workspace allows {limit} member account(s). Contact an operator to request more access."
)
_AI_LIMIT_MESSAGE = "Monthly AI analysis limit reached for this plan"


async def reserve_site_slot(session: AsyncSession, org_id: int) -> None:
    """Atomically reserve one site slot in the caller's transaction."""
    actual = select(func.count(Site.id)).where(Site.organization_id == org_id).scalar_subquery()
    reconciled = case(
        (Organization.site_slots_used < actual, actual),
        else_=Organization.site_slots_used,
    )
    statement = (
        update(Organization)
        .where(
            Organization.id == org_id,
            Organization.is_active.is_(True),
            or_(Organization.max_sites.is_(None), reconciled < Organization.max_sites),
        )
        .values(site_slots_used=reconciled + 1)
        .returning(Organization.id)
    )
    if (await session.execute(statement)).first() is not None:
        return
    await _raise_site_reservation_failure(session, org_id)


async def release_site_slot(session: AsyncSession, org_id: int) -> None:
    """Release the slot for a site that will be deleted in this transaction.

    Call this before deleting the Site so every create/delete path locks the
    organization row before touching the resource row, avoiding lock inversion.
    """
    actual = select(func.count(Site.id)).where(Site.organization_id == org_id).scalar_subquery()
    reconciled = case(
        (Organization.site_slots_used < actual, actual),
        else_=Organization.site_slots_used,
    )
    remaining = case((reconciled > 0, reconciled - 1), else_=0)
    await session.execute(
        update(Organization).where(Organization.id == org_id).values(site_slots_used=remaining)
    )


async def reserve_member_slot(session: AsyncSession, org_id: int) -> None:
    """Atomically reserve one non-operator member account in the transaction.

    The organization row serializes competing creates. The persisted counter is
    also reconciled upward from the underlying users so imports or legacy writes
    cannot make quota enforcement under-count existing tenant identities.
    """
    actual = (
        select(func.count(User.id))
        .where(
            User.organization_id == org_id,
            User.is_superadmin.is_(False),
        )
        .execution_options(skip_org_filter=True)
        .scalar_subquery()
    )
    reconciled = case(
        (Organization.member_slots_used < actual, actual),
        else_=Organization.member_slots_used,
    )
    statement = (
        update(Organization)
        .where(
            Organization.id == org_id,
            Organization.is_active.is_(True),
            or_(Organization.max_members.is_(None), reconciled < Organization.max_members),
        )
        .values(member_slots_used=reconciled + 1)
        .returning(Organization.id)
    )
    if (await session.execute(statement)).first() is not None:
        return
    await _raise_member_reservation_failure(session, org_id)


async def release_member_slot(session: AsyncSession, org_id: int) -> None:
    """Release the slot for a tenant member deleted in this transaction."""
    actual = (
        select(func.count(User.id))
        .where(
            User.organization_id == org_id,
            User.is_superadmin.is_(False),
        )
        .execution_options(skip_org_filter=True)
        .scalar_subquery()
    )
    reconciled = case(
        (Organization.member_slots_used < actual, actual),
        else_=Organization.member_slots_used,
    )
    remaining = case((reconciled > 0, reconciled - 1), else_=0)
    await session.execute(
        update(Organization).where(Organization.id == org_id).values(member_slots_used=remaining)
    )


async def reserve_ai_check(session: AsyncSession, org_id: int) -> None:
    """Atomically consume one AI attempt for the current UTC month.

    The reservation is intentionally committed before the external model call
    by ``SiteRunner``. A process crash may conservatively keep a slot consumed,
    but it can never let concurrent calls overspend the tenant cap.
    """
    month_key, month_start = _current_month()
    actual = (
        select(func.count(AIUsage.id))
        .where(
            AIUsage.organization_id == org_id,
            AIUsage.created_at >= month_start,
        )
        .scalar_subquery()
    )
    counter = case(
        (Organization.ai_usage_month == month_key, Organization.ai_checks_reserved),
        else_=0,
    )
    reconciled = case((counter < actual, actual), else_=counter)
    statement = (
        update(Organization)
        .where(
            Organization.id == org_id,
            Organization.is_active.is_(True),
            or_(
                Organization.monthly_ai_check_limit.is_(None),
                reconciled < Organization.monthly_ai_check_limit,
            ),
        )
        .values(ai_usage_month=month_key, ai_checks_reserved=reconciled + 1)
        .returning(Organization.id)
    )
    if (await session.execute(statement)).first() is not None:
        return
    await _raise_ai_reservation_failure(session, org_id)


async def ai_check_limit_reached(session: AsyncSession, org_id: int) -> bool:
    """Read-only quota status used by APIs and operator summaries."""
    org = await session.get(Organization, org_id)
    if org is None or not org.is_active:
        return True
    if org.monthly_ai_check_limit is None:
        return False
    month_key, month_start = _current_month()
    actual = (
        await session.execute(
            select(func.count(AIUsage.id)).where(
                AIUsage.organization_id == org_id,
                AIUsage.created_at >= month_start,
            )
        )
    ).scalar_one()
    reserved = org.ai_checks_reserved if org.ai_usage_month == month_key else 0
    return max(actual, reserved) >= org.monthly_ai_check_limit


async def _raise_site_reservation_failure(session: AsyncSession, org_id: int) -> None:
    org = await session.get(Organization, org_id)
    if org is None or not org.is_active:
        raise AccessDenied("This organization is suspended or no longer exists")
    if org.max_sites is None:
        raise AccessDenied("Unable to reserve a site slot")
    raise PlanLimitReached(_SITE_LIMIT_MESSAGE.format(limit=org.max_sites))


async def _raise_member_reservation_failure(session: AsyncSession, org_id: int) -> None:
    org = await session.get(Organization, org_id)
    if org is None or not org.is_active:
        raise AccessDenied("This organization is suspended or no longer exists")
    if org.max_members is None:
        raise AccessDenied("Unable to reserve a member slot")
    raise PlanLimitReached(_MEMBER_LIMIT_MESSAGE.format(limit=org.max_members))


async def _raise_ai_reservation_failure(session: AsyncSession, org_id: int) -> None:
    org = await session.get(Organization, org_id)
    if org is None or not org.is_active:
        raise AccessDenied("This organization is suspended or no longer exists")
    raise PlanLimitReached(_AI_LIMIT_MESSAGE)


def _current_month() -> tuple[str, datetime]:
    now = datetime.now(UTC)
    return f"{now.year:04d}-{now.month:02d}", datetime(now.year, now.month, 1, tzinfo=UTC)
