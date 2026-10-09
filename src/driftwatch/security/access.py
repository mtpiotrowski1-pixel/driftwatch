"""Edit-scope checks for the shared workspace.

Every signed-in member may *read* all shared data. Editing is restricted:
administrators may edit anything, and other members only what they have been
granted — a whole project (and the sites within it) or an individual site.
Creating a project is a structural change reserved for administrators.
"""

from __future__ import annotations

from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.exceptions import AccessDenied, NotFoundError
from driftwatch.models import (
    Project,
    Recipient,
    Site,
    User,
    project_editors,
    project_recipients,
    site_editors,
    site_recipients,
)


async def can_edit_project(session: AsyncSession, user: User, project_id: int) -> bool:
    if user.is_admin:
        return True
    return await _has_grant(session, project_editors, "project_id", project_id, user.id)


async def can_edit_site(session: AsyncSession, user: User, site: Site) -> bool:
    if user.is_admin:
        return True
    if await _has_grant(session, site_editors, "site_id", site.id, user.id):
        return True
    if site.project_id is not None:
        return await _has_grant(session, project_editors, "project_id", site.project_id, user.id)
    return False


async def require_site_edit(session: AsyncSession, user: User, site: Site) -> None:
    if not await can_edit_site(session, user, site):
        raise AccessDenied("You do not have edit access to this site")


async def require_project_edit(session: AsyncSession, user: User, project_id: int) -> None:
    if not await can_edit_project(session, user, project_id):
        raise AccessDenied("You do not have edit access to this project")


async def require_site_create(session: AsyncSession, user: User, project_id: int | None) -> None:
    # A site attached to a project inherits that project's notification
    # recipients, so a target project must be visible in the caller's scope.
    # The org-scope listener confines this lookup, so a cross-org (or unknown)
    # project reads as "not found" rather than leaking across the tenant via
    # the foreign key.
    if project_id is not None and await session.get(Project, project_id) is None:
        raise NotFoundError(f"Project {project_id} not found")
    if user.is_admin or user.is_superadmin:
        return
    if project_id is not None and await can_edit_project(session, user, project_id):
        return
    raise AccessDenied("You may only add sites to projects you can edit")


async def require_recipient_access(session: AsyncSession, user: User, recipient_id: int) -> None:
    """Allow managing a recipient (edit/delete/substitution) only to the operator,
    an admin of the recipient's own organization, or a member who can edit at least
    one site or project that notifies it — so neither a lone grant nor another org's
    admin can redirect or delete an out-of-scope recipient."""
    if user.is_superadmin:
        return
    # The recipient is org-scoped: a cross-org id does not resolve on this session,
    # so this also confines an org-admin to recipients in their own organization.
    recipient = await session.get(Recipient, recipient_id)
    if recipient is None:
        raise AccessDenied("You do not have access to this recipient")
    if user.is_admin:
        return
    sites = (
        await session.execute(
            select(Site)
            .join(site_recipients, Site.id == site_recipients.c.site_id)
            .where(site_recipients.c.recipient_id == recipient_id)
        )
    ).scalars()
    for site in sites:
        if await can_edit_site(session, user, site):
            return
    project_ids = (
        await session.execute(
            select(project_recipients.c.project_id).where(
                project_recipients.c.recipient_id == recipient_id
            )
        )
    ).scalars()
    for project_id in project_ids:
        if await can_edit_project(session, user, project_id):
            return
    raise AccessDenied("You do not have access to this recipient")


async def require_any_edit(session: AsyncSession, user: User) -> None:
    """Allow admins and anyone holding at least one project or site edit grant."""
    if user.is_admin:
        return
    for table in (project_editors, site_editors):
        if (
            await session.execute(select(table.c.user_id).where(table.c.user_id == user.id))
        ).first() is not None:
            return
    raise AccessDenied("You need edit access to use this")


async def _has_grant(
    session: AsyncSession, table: Table, column: str, owner_id: int, user_id: int
) -> bool:
    stmt = select(table.c[column]).where(
        table.c[column] == owner_id,
        table.c.user_id == user_id,
    )
    return (await session.execute(stmt)).first() is not None
