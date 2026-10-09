"""Reusable persistence helpers shared across routers.

Many-to-many recipient links are managed directly on the association tables
rather than through ORM relationship collections: it keeps the operations
explicit and avoids lazy-loading a collection inside async request handlers.
"""

from __future__ import annotations

from sqlalchemy import Table, delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.exceptions import ConflictError
from driftwatch.models import Organization, Recipient, project_recipients, site_recipients
from driftwatch.monitoring.prompts import ResolvedRules, resolve_importance_rules
from driftwatch.security.crypto import SecretBox
from driftwatch.settings_store import SettingsStore


async def ensure_default_organization(session: AsyncSession, name: str) -> Organization:
    """Return the lowest-id organization, creating one if the instance has none.
    Used to bootstrap the seeded superadmin and to home self-registered users."""
    org = (
        await session.execute(select(Organization).order_by(Organization.id).limit(1))
    ).scalar_one_or_none()
    if org is None:
        org = Organization(name=name)
        session.add(org)
        await session.flush()
    return org


async def _validate_recipient_ids(session: AsyncSession, recipient_ids: list[int]) -> list[int]:
    unique = list(dict.fromkeys(recipient_ids))
    if not unique:
        return []
    found = set(
        (await session.execute(select(Recipient.id).where(Recipient.id.in_(unique)))).scalars()
    )
    missing = [rid for rid in unique if rid not in found]
    if missing:
        raise ConflictError(f"unknown recipient ids: {missing}")
    return unique


async def _replace_links(
    session: AsyncSession, table: Table, owner_column: str, owner_id: int, recipient_ids: list[int]
) -> None:
    valid = await _validate_recipient_ids(session, recipient_ids)
    await session.execute(delete(table).where(table.c[owner_column] == owner_id))
    if valid:
        await session.execute(
            insert(table),
            [{owner_column: owner_id, "recipient_id": rid} for rid in valid],
        )


async def set_site_recipients(
    session: AsyncSession, site_id: int, recipient_ids: list[int]
) -> None:
    await _replace_links(session, site_recipients, "site_id", site_id, recipient_ids)


async def set_project_recipients(
    session: AsyncSession, project_id: int, recipient_ids: list[int]
) -> None:
    await _replace_links(session, project_recipients, "project_id", project_id, recipient_ids)


async def site_recipient_ids(session: AsyncSession, site_ids: list[int]) -> dict[int, list[int]]:
    return await _link_map(session, site_recipients, "site_id", site_ids)


async def project_recipient_ids(
    session: AsyncSession, project_ids: list[int]
) -> dict[int, list[int]]:
    return await _link_map(session, project_recipients, "project_id", project_ids)


async def _link_map(
    session: AsyncSession, table: Table, owner_column: str, owner_ids: list[int]
) -> dict[int, list[int]]:
    result: dict[int, list[int]] = {owner_id: [] for owner_id in owner_ids}
    if not owner_ids:
        return result
    rows = await session.execute(
        select(table.c[owner_column], table.c.recipient_id).where(
            table.c[owner_column].in_(owner_ids)
        )
    )
    for owner_id, recipient_id in rows:
        result[owner_id].append(recipient_id)
    return result


async def effective_importance_rules(
    session: AsyncSession,
    box: SecretBox,
    *,
    org_id: int | None,
    site_prompt: str | None = None,
    project_prompt: str | None = None,
) -> ResolvedRules:
    """Resolve the importance rules in effect at a given inheritance level.

    Mirrors exactly what the runner feeds the analyzer (site prompt, else
    project prompt, else the org's global rules, else the built-in default), so
    the UI can show which rules currently apply and where they come from.
    """
    store = SettingsStore(session, box, org_id=org_id)
    return resolve_importance_rules(
        site_prompt=site_prompt,
        project_prompt=project_prompt,
        global_rules=await store.importance_rules(),
    )
