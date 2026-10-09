"""Time-limited, audited operator access to a customer organization."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from driftwatch.api.deps import (
    SUPPORT_ACCESS_COOKIE,
    SUPPORT_ACCESS_TTL_SECONDS,
    SessionDep,
    SettingsDep,
    StepUpUser,
    SuperadminUser,
    current_support_access,
    operator_support_access_required,
)
from driftwatch.audit import record_audit_event
from driftwatch.models import Organization, SupportAccessGrant
from driftwatch.schemas import SupportAccessOut, SupportAccessRequest
from driftwatch.security.tokens import issue_support_access_token

router = APIRouter(prefix="/api/support-access", tags=["support-access"])


def _acting_organization_id(session: SessionDep) -> int:
    organization_id = session.sync_session.info.get("org_id")
    if organization_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Enter an organization before requesting support access",
        )
    return int(organization_id)


@router.get("", response_model=SupportAccessOut)
async def get_support_access(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    admin: SuperadminUser,
) -> SupportAccessOut:
    organization_id = _acting_organization_id(session)
    claims = await current_support_access(request, session, admin, settings, organization_id)
    required = operator_support_access_required(admin, settings, organization_id)
    return SupportAccessOut(
        required=required,
        access_enabled=not required or claims is not None,
        organization_id=organization_id,
        expires_at=claims.expires_at if claims else None,
    )


@router.post("", response_model=SupportAccessOut)
async def grant_support_access(
    payload: SupportAccessRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    admin: SuperadminUser,
    _: StepUpUser,
) -> SupportAccessOut:
    organization_id = _acting_organization_id(session)
    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Acting organization not found")
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(seconds=SUPPORT_ACCESS_TTL_SECONDS)
    revoked = await session.execute(
        update(SupportAccessGrant)
        .where(
            SupportAccessGrant.operator_user_id == admin.id,
            SupportAccessGrant.organization_id == organization.id,
            SupportAccessGrant.revoked_at.is_(None),
        )
        .values(revoked_at=issued_at, active_marker=None)
    )
    revoked_count = max(int(revoked.rowcount or 0), 0)  # type: ignore[attr-defined]
    event = record_audit_event(
        session,
        request,
        admin,
        action="support.access_granted",
        target_type="organization",
        target_id=organization.id,
        target_label=organization.name,
        organization_id=organization.id,
        details={
            "reason": payload.reason,
            "ticket": payload.ticket,
            "expires_at": expires_at.isoformat(),
            "revoked_previous_grants": revoked_count,
        },
    )
    await session.flush()
    session.add(
        SupportAccessGrant(
            operator_user_id=admin.id,
            organization_id=organization.id,
            grant_event_id=event.id,
            active_marker=True,
            expires_at=expires_at,
        )
    )
    try:
        await session.flush()
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Another support access grant was created concurrently",
        ) from exc
    token = issue_support_access_token(
        admin.id,
        organization_id=organization.id,
        grant_event_id=event.id,
        secret=settings.token_secret,
        ttl_seconds=SUPPORT_ACCESS_TTL_SECONDS,
        token_version=admin.token_version,
        session_generation=admin.session_generation,
    )
    response.set_cookie(
        SUPPORT_ACCESS_COOKIE,
        token,
        max_age=SUPPORT_ACCESS_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=not settings.is_local,
        path="/api",
    )
    return SupportAccessOut(
        required=operator_support_access_required(admin, settings, organization_id),
        access_enabled=True,
        organization_id=organization.id,
        expires_at=expires_at,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_support_access(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    admin: SuperadminUser,
) -> None:
    organization_id = _acting_organization_id(session)
    claims = await current_support_access(request, session, admin, settings, organization_id)
    revoked_at = datetime.now(UTC)
    result = await session.execute(
        update(SupportAccessGrant)
        .where(
            SupportAccessGrant.operator_user_id == admin.id,
            SupportAccessGrant.organization_id == organization_id,
            SupportAccessGrant.revoked_at.is_(None),
        )
        .values(revoked_at=revoked_at, active_marker=None)
    )
    revoked_count = max(int(result.rowcount or 0), 0)  # type: ignore[attr-defined]
    if revoked_count:
        organization = await session.get(Organization, organization_id)
        record_audit_event(
            session,
            request,
            admin,
            action="support.access_revoked",
            target_type="organization",
            target_id=organization_id,
            target_label=organization.name if organization else None,
            organization_id=organization_id,
            details={
                "grant_event_id": claims.grant_event_id if claims is not None else None,
                "revoked_grants": revoked_count,
            },
        )
    await session.commit()
    response.delete_cookie(SUPPORT_ACCESS_COOKIE, path="/api")
