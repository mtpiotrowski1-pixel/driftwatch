"""Instance-level lifecycle management for privileged operator identities."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from driftwatch.account_mail import enqueue_account_invitation
from driftwatch.api.deps import (
    InstanceSuperadminUser,
    LoginThrottleDep,
    SessionDep,
    StepUpUser,
)
from driftwatch.audit import record_audit_event
from driftwatch.models import User
from driftwatch.schemas import OperatorCreate, OperatorOut, OperatorUpdate
from driftwatch.security.passwords import ahash_password

router = APIRouter(prefix="/api/operators", tags=["operators"])

_INVITATION_RESEND_LIMIT = 3
_LAST_ACTIVE_DETAIL = "The last active operator cannot be deactivated"


@router.get("", response_model=list[OperatorOut])
async def list_operators(session: SessionDep, _: InstanceSuperadminUser) -> list[OperatorOut]:
    rows = (
        await session.execute(
            select(User)
            .where(User.is_superadmin.is_(True))
            .order_by(User.email)
            .execution_options(skip_org_filter=True)
        )
    ).scalars()
    return [OperatorOut.model_validate(row) for row in rows]


@router.post("", response_model=OperatorOut, status_code=status.HTTP_201_CREATED)
async def create_operator(
    payload: OperatorCreate,
    request: Request,
    session: SessionDep,
    admin: InstanceSuperadminUser,
    _: StepUpUser,
) -> OperatorOut:
    operator = User(
        email=payload.email.lower(),
        name=payload.name,
        password_hash=await ahash_password(secrets.token_urlsafe(48)),
        organization_id=None,
        is_admin=True,
        is_superadmin=True,
        is_active=True,
    )
    session.add(operator)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already in use") from exc
    await enqueue_account_invitation(session, user=operator)
    record_audit_event(
        session,
        request,
        admin,
        action="operator.created",
        target_type="operator",
        target_id=operator.id,
        target_label=operator.email,
        organization_id=None,
        details={"invitation_delivery": "scheduled"},
    )
    return OperatorOut.model_validate(operator)


@router.patch("/{operator_id}", response_model=OperatorOut)
async def update_operator(
    operator_id: int,
    payload: OperatorUpdate,
    request: Request,
    session: SessionDep,
    admin: InstanceSuperadminUser,
    _: StepUpUser,
) -> OperatorOut:
    operator = await _require_operator(session, operator_id)
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No operator changes were requested")
    if fields.get("email"):
        fields["email"] = fields["email"].lower()

    deactivating = fields.get("is_active") is False and operator.is_active
    if deactivating:
        await _protect_last_active_operator(session, operator.id)
        if operator.id == admin.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate yourself")

    before = {field: getattr(operator, field) for field in fields}
    for key, value in fields.items():
        setattr(operator, key, value)
    changes = {
        field: {"from": before[field], "to": getattr(operator, field)}
        for field in before
        if before[field] != getattr(operator, field)
    }
    if not changes:
        return OperatorOut.model_validate(operator)
    if changes.keys() & {"email", "is_active"}:
        operator.token_version += 1
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already in use") from exc
    record_audit_event(
        session,
        request,
        admin,
        action="operator.updated",
        target_type="operator",
        target_id=operator.id,
        target_label=operator.email,
        organization_id=None,
        details={"changes": changes},
    )
    return OperatorOut.model_validate(operator)


@router.post("/{operator_id}/invite", status_code=status.HTTP_204_NO_CONTENT)
async def invite_operator(
    operator_id: int,
    request: Request,
    session: SessionDep,
    throttle: LoginThrottleDep,
    admin: InstanceSuperadminUser,
    _: StepUpUser,
) -> None:
    operator = await _require_operator(session, operator_id)
    if not operator.is_active:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Reactivate the operator before sending a password setup link",
        )
    retry_after = await throttle.consume(
        f"operator-invitation:{admin.id}:{operator.id}",
        max_actions=_INVITATION_RESEND_LIMIT,
    )
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many invitations. Please wait and try again.",
            headers={"Retry-After": str(int(retry_after))},
        )
    await enqueue_account_invitation(session, user=operator)
    record_audit_event(
        session,
        request,
        admin,
        action="operator.invitation_queued",
        target_type="operator",
        target_id=operator.id,
        target_label=operator.email,
        organization_id=None,
        details={"delivery": "scheduled"},
    )


@router.post("/{operator_id}/revoke-sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_operator_sessions(
    operator_id: int,
    request: Request,
    session: SessionDep,
    admin: InstanceSuperadminUser,
    _: StepUpUser,
) -> None:
    operator = await _require_operator(session, operator_id)
    operator.token_version += 1
    record_audit_event(
        session,
        request,
        admin,
        action="operator.sessions_revoked",
        target_type="operator",
        target_id=operator.id,
        target_label=operator.email,
        organization_id=None,
    )


@router.post("/{operator_id}/reset-totp", status_code=status.HTTP_204_NO_CONTENT)
async def reset_operator_totp(
    operator_id: int,
    request: Request,
    session: SessionDep,
    admin: InstanceSuperadminUser,
    _: StepUpUser,
) -> None:
    operator = await _require_operator(session, operator_id)
    operator.totp_enabled = False
    operator.totp_secret = None
    operator.recovery_code_hashes = []
    operator.token_version += 1
    record_audit_event(
        session,
        request,
        admin,
        action="operator.totp_reset",
        target_type="operator",
        target_id=operator.id,
        target_label=operator.email,
        organization_id=None,
    )


async def _require_operator(session: SessionDep, operator_id: int) -> User:
    operator = (
        await session.execute(
            select(User)
            .where(User.id == operator_id, User.is_superadmin.is_(True))
            .execution_options(skip_org_filter=True)
        )
    ).scalar_one_or_none()
    if operator is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Operator {operator_id} not found")
    return operator


async def _protect_last_active_operator(session: SessionDep, operator_id: int) -> None:
    active_ids = list(
        (
            await session.execute(
                select(User.id)
                .where(User.is_superadmin.is_(True), User.is_active.is_(True))
                .execution_options(skip_org_filter=True)
                .with_for_update()
            )
        ).scalars()
    )
    if active_ids == [operator_id]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _LAST_ACTIVE_DETAIL)
