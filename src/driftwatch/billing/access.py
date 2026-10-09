"""Database locking contract for organization access-state writers."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.models import Organization


async def lock_organization_access(
    session: AsyncSession,
    organization_id: int,
) -> Organization | None:
    """Lock and refresh an organization before changing its access state.

    The access-writer order is ``BillingCustomer`` then ``Organization`` then
    ``Subscription``. Writers that take only this lock must not later acquire a
    billing-customer lock or mutate a subscription in the same transaction.
    """
    return (
        await session.execute(
            select(Organization)
            .where(Organization.id == organization_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
