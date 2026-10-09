"""Administrator management of accounts and their edit permissions."""

from __future__ import annotations

import secrets
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import Table, delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from driftwatch.account_mail import enqueue_account_invitation
from driftwatch.api.deps import (
    AdminUser,
    LoginThrottleDep,
    OrgContext,
    SessionDep,
    SettingsDep,
    StepUpUser,
    require_step_up,
)
from driftwatch.audit import record_audit_event
from driftwatch.models import CheckoutAttempt, Project, Site, User, project_editors, site_editors
from driftwatch.quota import release_member_slot, reserve_member_slot
from driftwatch.schemas import (
    PermissionsUpdate,
    UserCreate,
    UserDetail,
    UserUpdate,
)
from driftwatch.security.passwords import ahash_password

router = APIRouter(prefix="/api/users", tags=["users"])

_INVITATION_RESEND_LIMIT = 3
_USER_CREATION_LIMIT = 10


@router.get("", response_model=list[UserDetail])
async def list_users(session: SessionDep, admin: AdminUser) -> list[UserDetail]:
    # Operator identities are managed only through the dedicated control plane,
    # even when a legacy/bootstrap operator shares a tenant's home organization.
    statement = select(User).where(User.is_superadmin.is_(False))
    users = list((await session.execute(statement.order_by(User.email))).scalars())
    user_ids = [user.id for user in users]
    projects = await _grant_map(session, project_editors, "project_id", user_ids)
    sites = await _grant_map(session, site_editors, "site_id", user_ids)

    result: list[UserDetail] = []
    for user in users:
        detail = UserDetail.model_validate(user)
        detail.project_ids = projects.get(user.id, [])
        detail.site_ids = sites.get(user.id, [])
        result.append(detail)
    return result


@router.post("", response_model=UserDetail, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    throttle: LoginThrottleDep,
    admin: AdminUser,
    org_id: OrgContext,
) -> UserDetail:
    # Every newly created identity grants access to tenant data, regardless of
    # role, so creation always requires recent re-authentication.
    await require_step_up(request, admin, settings)
    retry_after = await throttle.consume(
        f"user-create:{admin.id}:{org_id}",
        max_actions=_USER_CREATION_LIMIT,
    )
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many account creations. Please wait and try again.",
            headers={"Retry-After": str(int(retry_after))},
        )
    # Reserve before hashing or scheduling mail. A rejected request therefore
    # consumes neither an expensive password hash nor any durable account data.
    await reserve_member_slot(session, org_id)
    # The new account joins the active organization: an org-admin's own org, or
    # the one the operator has entered.
    user = User(
        email=payload.email.lower(),
        name=payload.name,
        # The administrator never chooses or learns the credential. Until the
        # invitation is consumed this random technical password is not usable in
        # practice and is never returned, logged, or persisted raw.
        password_hash=await ahash_password(secrets.token_urlsafe(48)),
        is_admin=payload.is_admin,
        organization_id=org_id,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already in use") from exc
    await enqueue_account_invitation(session, user=user)
    record_audit_event(
        session,
        request,
        admin,
        action="user.created",
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        organization_id=user.organization_id,
        details={"is_admin": user.is_admin, "invitation_delivery": "scheduled"},
    )
    return UserDetail.model_validate(user)


@router.patch("/{user_id}", response_model=UserDetail)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    admin: AdminUser,
) -> UserDetail:
    user = await _require_manageable_user(session, user_id, admin)
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("email"):
        fields["email"] = fields["email"].lower()
    sensitive_change = any(
        field in fields and fields[field] != getattr(user, field)
        for field in ("email", "is_admin", "is_active")
    )
    if sensitive_change:
        await require_step_up(request, admin, settings)
    before = {field: getattr(user, field) for field in ("email", "name", "is_admin", "is_active")}
    await _protect_last_active_superadmin(
        session,
        user,
        demoting=fields.get("is_admin") is False,
        deactivating=fields.get("is_active") is False,
    )
    if user.id == admin.id:
        if fields.get("is_admin") is False:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "You cannot remove your own admin role"
            )
        if fields.get("is_active") is False:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate yourself")
    for key, value in fields.items():
        setattr(user, key, value)
    if sensitive_change:
        # Email, role, and activation changes alter the account's trust boundary.
        # Revoke all sessions even when the current administrator edits themself.
        user.token_version += 1
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already in use") from exc
    changes = {
        field: {"from": before[field], "to": getattr(user, field)}
        for field in before
        if before[field] != getattr(user, field)
    }
    if changes:
        record_audit_event(
            session,
            request,
            admin,
            action="user.updated",
            target_type="user",
            target_id=user.id,
            target_label=user.email,
            organization_id=user.organization_id,
            details={"changes": changes},
        )
    return await _detail(session, user)


@router.post("/{user_id}/invite", status_code=status.HTTP_204_NO_CONTENT)
async def invite_user(
    user_id: int,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    throttle: LoginThrottleDep,
    admin: AdminUser,
) -> None:
    # Resolve the tenant-scoped target before issuing a step-up challenge so a
    # foreign identifier remains indistinguishable from a missing account.
    user = await _require_manageable_user(session, user_id, admin)
    await require_step_up(request, admin, settings)
    if not user.is_active:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Activate the user before sending a password setup link",
        )

    retry_after = await throttle.consume(
        f"user-invitation:{admin.id}:{user.id}",
        max_actions=_INVITATION_RESEND_LIMIT,
    )
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many invitations. Please wait and try again.",
            headers={"Retry-After": str(int(retry_after))},
        )

    await enqueue_account_invitation(session, user=user)
    record_audit_event(
        session,
        request,
        admin,
        action="user.invitation_queued",
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        organization_id=user.organization_id,
        details={"delivery": "scheduled"},
    )


@router.post("/{user_id}/revoke-sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_user_sessions(
    user_id: int,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
    _: StepUpUser,
) -> None:
    user = await _require_manageable_user(session, user_id, admin)
    user.token_version += 1
    record_audit_event(
        session,
        request,
        admin,
        action="user.sessions_revoked",
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        organization_id=user.organization_id,
    )


@router.post("/{user_id}/reset-totp", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_totp(
    user_id: int,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
    _: StepUpUser,
) -> None:
    user = await _require_manageable_user(session, user_id, admin)
    user.totp_enabled = False
    user.totp_secret = None
    user.recovery_code_hashes = []
    user.token_version += 1
    record_audit_event(
        session,
        request,
        admin,
        action="user.totp_reset",
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        organization_id=user.organization_id,
    )


@router.put("/{user_id}/permissions", response_model=UserDetail)
async def set_permissions(
    user_id: int,
    payload: PermissionsUpdate,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    admin: AdminUser,
) -> UserDetail:
    user = await _require_manageable_user(session, user_id, admin)
    await require_step_up(request, admin, settings)
    # The grant association tables carry no org column, so validate the ids on the
    # org-scoped session first — a cross-org project/site id won't resolve here.
    await _require_in_scope(session, Project.id, payload.project_ids)
    await _require_in_scope(session, Site.id, payload.site_ids)
    await _replace_grants(session, project_editors, "project_id", user_id, payload.project_ids)
    await _replace_grants(session, site_editors, "site_id", user_id, payload.site_ids)
    record_audit_event(
        session,
        request,
        admin,
        action="user.permissions_updated",
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        organization_id=user.organization_id,
        details={"project_ids": payload.project_ids, "site_ids": payload.site_ids},
    )
    return await _detail(session, user)


async def _require_in_scope(
    session: AsyncSession, id_column: InstrumentedAttribute[int], ids: list[int]
) -> None:
    unique = list(dict.fromkeys(ids))
    if not unique:
        return
    found = set((await session.execute(select(id_column).where(id_column.in_(unique)))).scalars())
    missing = [owner_id for owner_id in unique if owner_id not in found]
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown or out-of-scope ids: {missing}")


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    admin: AdminUser,
) -> None:
    user = await _require_manageable_user(session, user_id, admin)
    # Resolve the tenant-scoped target first so a foreign id remains a uniform
    # 404 rather than revealing its existence through a step-up challenge.
    await require_step_up(request, admin, settings)
    await _protect_last_active_superadmin(session, user, deleting=True)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own account")
    billing_reference = await session.scalar(
        select(CheckoutAttempt.id).where(CheckoutAttempt.requested_by_user_id == user.id).limit(1)
    )
    if billing_reference is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This account has billing history and must be deactivated rather than deleted",
        )
    target_id = user.id
    target_email = user.email
    organization_id = user.organization_id
    if organization_id is not None:
        await release_member_slot(session, organization_id)
    await session.delete(user)
    try:
        # Surface any future retention FK as a stable conflict before the
        # response is created, instead of leaking an IntegrityError at commit.
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This account has retained history and must be deactivated rather than deleted",
        ) from exc
    record_audit_event(
        session,
        request,
        admin,
        action="user.deleted",
        target_type="user",
        target_id=target_id,
        target_label=target_email,
        organization_id=organization_id,
    )


async def _require_user(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"User {user_id} not found")
    return user


async def _require_manageable_user(session: AsyncSession, user_id: int, admin: User) -> User:
    """Resolve an account without exposing operator identities to tenant admins."""
    user = await _require_user(session, user_id)
    if user.is_superadmin:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"User {user_id} not found")
    return user


async def _protect_last_active_superadmin(
    session: AsyncSession,
    user: User,
    *,
    demoting: bool = False,
    deactivating: bool = False,
    deleting: bool = False,
) -> None:
    """Keep at least one active operator account available for recovery."""
    if not user.is_superadmin or not user.is_active:
        return
    if not (demoting or deactivating or deleting):
        return

    # Acting-org sessions are tenant-scoped. Bypass that read filter and lock the
    # active operator rows so concurrent administrative changes serialize on
    # databases that support SELECT FOR UPDATE (SQLite serializes writes itself).
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
    if active_ids == [user.id]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The last active operator cannot be demoted, deactivated, or deleted",
        )


async def _detail(session: AsyncSession, user: User) -> UserDetail:
    detail = UserDetail.model_validate(user)
    grants = [user.id]
    detail.project_ids = (await _grant_map(session, project_editors, "project_id", grants)).get(
        user.id, []
    )
    detail.site_ids = (await _grant_map(session, site_editors, "site_id", grants)).get(user.id, [])
    return detail


async def _grant_map(
    session: AsyncSession, table: Table, column: str, user_ids: list[int]
) -> dict[int, list[int]]:
    # Scope the read to the given users (the caller's own organization). The grant
    # tables carry no org column, so an unfiltered read would scan every tenant's
    # grants — confining it by user id both isolates and keeps the query cheap as
    # the instance accrues organizations.
    grants: dict[int, list[int]] = defaultdict(list)
    if not user_ids:
        return grants
    rows = await session.execute(
        select(table.c.user_id, table.c[column]).where(table.c.user_id.in_(user_ids))
    )
    for user_id, owner_id in rows:
        grants[user_id].append(owner_id)
    return grants


async def _replace_grants(
    session: AsyncSession, table: Table, column: str, user_id: int, owner_ids: list[int]
) -> None:
    await session.execute(delete(table).where(table.c.user_id == user_id))
    unique = list(dict.fromkeys(owner_ids))
    if unique:
        await session.execute(
            insert(table), [{"user_id": user_id, column: owner_id} for owner_id in unique]
        )
