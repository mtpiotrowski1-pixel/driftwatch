"""Recipient CRUD. Recipients receive change notifications per site or project."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.api.deps import CurrentUser, OrgContext, SessionDep
from driftwatch.models import Project, Recipient, RecipientSubstitution, Site
from driftwatch.schemas import (
    RecipientCreate,
    RecipientOut,
    RecipientUpdate,
    SubstitutionCreate,
    SubstitutionOut,
)
from driftwatch.security.access import require_any_edit, require_recipient_access

router = APIRouter(prefix="/api/recipients", tags=["recipients"])


@router.get("", response_model=list[RecipientOut])
async def list_recipients(session: SessionDep, _: CurrentUser) -> list[Recipient]:
    return list((await session.execute(select(Recipient).order_by(Recipient.email))).scalars())


@router.post("", response_model=RecipientOut, status_code=status.HTTP_201_CREATED)
async def create_recipient(
    payload: RecipientCreate, session: SessionDep, user: CurrentUser, org_id: OrgContext
) -> Recipient:
    await require_any_edit(session, user)
    recipient = Recipient(organization_id=org_id, email=payload.email.lower(), name=payload.name)
    session.add(recipient)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A recipient with this email already exists"
        ) from exc
    return recipient


@router.patch("/{recipient_id}", response_model=RecipientOut)
async def update_recipient(
    recipient_id: int, payload: RecipientUpdate, session: SessionDep, user: CurrentUser
) -> Recipient:
    # Existence (404) is checked before edit access (403): an out-of-scope
    # recipient is filtered away by the org-scope listener and must read as
    # "not found" rather than leak its existence with a 403.
    recipient = await _require_recipient(session, recipient_id)
    await require_recipient_access(session, user, recipient_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(recipient, key, value)
    return recipient


@router.delete("/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipient(recipient_id: int, session: SessionDep, user: CurrentUser) -> None:
    recipient = await _require_recipient(session, recipient_id)
    await require_recipient_access(session, user, recipient_id)
    await session.delete(recipient)


@router.get("/{recipient_id}/substitutions", response_model=list[SubstitutionOut])
async def list_substitutions(
    recipient_id: int, session: SessionDep, _: CurrentUser
) -> list[RecipientSubstitution]:
    await _require_recipient(session, recipient_id)
    rows = await session.execute(
        select(RecipientSubstitution)
        .where(RecipientSubstitution.recipient_id == recipient_id)
        .order_by(RecipientSubstitution.start_date)
    )
    return list(rows.scalars())


@router.post(
    "/{recipient_id}/substitutions",
    response_model=SubstitutionOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_substitution(
    recipient_id: int, payload: SubstitutionCreate, session: SessionDep, user: CurrentUser
) -> RecipientSubstitution:
    # Redirecting a recipient's mail is an exfiltration primitive — scope it.
    await _require_recipient(session, recipient_id)
    await require_recipient_access(session, user, recipient_id)
    # A scoped cover must point at a project/site the caller can see; the
    # org-scoped session resolves a foreign id to None, which reads as 404.
    if payload.project_id is not None and await session.get(Project, payload.project_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if payload.site_id is not None and await session.get(Site, payload.site_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    substitution = RecipientSubstitution(
        recipient_id=recipient_id,
        project_id=payload.project_id,
        site_id=payload.site_id,
        substitute_email=payload.substitute_email.lower(),
        substitute_name=payload.substitute_name,
        start_date=payload.start_date.isoformat(),
        end_date=payload.end_date.isoformat(),
    )
    session.add(substitution)
    await session.flush()
    return substitution


@router.delete("/substitutions/{substitution_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_substitution(substitution_id: int, session: SessionDep, user: CurrentUser) -> None:
    substitution = await session.get(RecipientSubstitution, substitution_id)
    # The substitution carries no org column, so confirm its recipient resolves
    # in the caller's scope: a cross-org id then reads as a uniform "not found"
    # (404) instead of revealing its existence with a 403.
    if substitution is None or await session.get(Recipient, substitution.recipient_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Substitution not found")
    await require_recipient_access(session, user, substitution.recipient_id)
    await session.delete(substitution)


async def _require_recipient(session: AsyncSession, recipient_id: int) -> Recipient:
    recipient = await session.get(Recipient, recipient_id)
    if recipient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Recipient {recipient_id} not found")
    return recipient
