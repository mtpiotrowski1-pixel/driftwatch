"""Transaction boundary for publishing immutable billing plan contracts."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.models import Plan


async def lock_plan_contract(session: AsyncSession, plan_id: int) -> Plan | None:
    """Lock and refresh a plan until the current transaction completes.

    Plan mutations and price publication use this same row lock. PostgreSQL can
    therefore never publish the first price concurrently with a contract-field
    edit that did not yet observe price history.
    """
    return (
        await session.execute(
            select(Plan)
            .where(Plan.id == plan_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
