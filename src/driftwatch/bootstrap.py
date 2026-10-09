"""Atomically claim a fresh instance once, using the database as the arbiter.

The migration creates a singleton and closes it for existing workspaces. The
claim is committed together with the administrator account, so failures release
the claim and concurrent registrations cannot both become instance operators.
User deletion never deletes or resets this independent record.
"""

from __future__ import annotations

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.models import InstanceBootstrap, Organization, User


async def initial_admin_signup_available(session: AsyncSession) -> bool:
    available = await session.scalar(
        select(InstanceBootstrap.id).where(
            InstanceBootstrap.id == 1,
            InstanceBootstrap.completed.is_(False),
            ~exists(select(User.id)),
            ~exists(select(Organization.id)),
        )
    )
    return available is not None


async def claim_initial_admin(session: AsyncSession) -> bool:
    """Make this the transaction's first database statement to avoid SQLite
    read-to-write snapshot upgrades. Postgres rechecks the predicate after any
    competing row lock; SQLite serializes the write before account creation.
    A missing singleton fails closed rather than inferring ownership from rows.
    """
    claimed = await session.scalar(
        update(InstanceBootstrap)
        .where(
            InstanceBootstrap.id == 1,
            InstanceBootstrap.completed.is_(False),
            ~exists(select(User.id)),
            ~exists(select(Organization.id)),
        )
        .values(completed=True)
        .returning(InstanceBootstrap.id)
    )
    return claimed is not None


async def close_existing_instance_bootstrap(session: AsyncSession) -> None:
    """Also protect accounts created outside signup since the schema upgrade."""
    await session.execute(
        update(InstanceBootstrap)
        .where(
            InstanceBootstrap.id == 1,
            InstanceBootstrap.completed.is_(False),
            exists(select(User.id)) | exists(select(Organization.id)),
        )
        .values(completed=True)
    )
