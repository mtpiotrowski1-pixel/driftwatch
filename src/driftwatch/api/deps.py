"""Shared FastAPI dependencies.

The application wires its long-lived collaborators (database, runner, settings,
secret box) onto ``app.state`` at startup; these accessors read them back and
expose authentication as ready-made ``Annotated`` types so routers stay terse.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import ORMExecuteState, with_loader_criteria

from driftwatch.audit import record_audit_event
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.maintenance import MaintenanceMode
from driftwatch.models import (
    AIUsage,
    BillingCustomer,
    CheckoutAttempt,
    EntitlementGrant,
    InteractionSecret,
    InvoiceReference,
    Organization,
    Project,
    Recipient,
    Site,
    SiteCheckJob,
    Subscription,
    SupportAccessGrant,
    User,
)
from driftwatch.monitoring.picker import PickerService
from driftwatch.runner import SiteRunner
from driftwatch.scheduler import MonitorScheduler
from driftwatch.security.crypto import SecretBox
from driftwatch.security.throttle import LoginThrottle
from driftwatch.security.tokens import (
    SessionError,
    SupportAccessClaims,
    read_session,
    read_step_up_token,
    read_support_access_token,
)
from driftwatch.settings_store import SettingsStore

SESSION_COOKIE = "driftwatch_session"
# Lets the operator (superadmin) "enter" an organization: scopes their reads to
# it and makes new resources land in it. Ignored for everyone else.
ACTING_ORG_HEADER = "x-acting-org"
# Set after the password but before the TOTP code on a 2FA login; exchanged for a
# real session by POST /api/auth/login/totp.
PENDING_TOTP_COOKIE = "driftwatch_2fa"
# Proof of a recent re-authentication, required by the most destructive actions.
STEP_UP_COOKIE = "driftwatch_stepup"
STEP_UP_TTL_SECONDS = 300
SUPPORT_ACCESS_COOKIE = "driftwatch_support_access"
SUPPORT_ACCESS_TTL_SECONDS = 900

# A public operator at instance scope may reach only this control plane. Every
# other authenticated route is tenant-owned and requires explicit X-Acting-Org
# context. Foreign workspaces also require a live, audited support-access grant;
# an operator with administrator membership may use their own home directly.
# Keeping the list positive prevents a newly added product endpoint from
# silently becoming an unfiltered cross-tenant read.
_INSTANCE_CONTROL_PLANE_PREFIXES = (
    "/api/admin",
    "/api/audit-events",
    "/api/auth",
    "/api/branding",
    "/api/operations",
    "/api/operators",
    "/api/organizations",
    "/api/plans",
    "/api/settings",
    "/api/support-access",
)
_INSTANCE_CONTROL_PLANE_EXACT_PATHS = frozenset({"/api/billing/prices"})

# A public-deployment administrator must enroll a second factor before the
# session can exercise any application or tenant capability. These endpoints
# are the smallest surface needed to finish enrollment (or inspect/end the
# session).
_MFA_ENROLLMENT_ENDPOINTS = frozenset(
    {
        ("GET", "/api/auth/me"),
        ("POST", "/api/auth/logout"),
        ("POST", "/api/auth/step-up"),
        ("POST", "/api/auth/totp/setup"),
        ("POST", "/api/auth/totp/enable"),
    }
)

# A billing-suspended tenant still needs the narrow recovery surface required to
# inspect its state, pay, or cancel. Every other application capability remains
# locked by the normal organization suspension check.
_BILLING_RECOVERY_ENDPOINTS = frozenset(
    {
        ("GET", "/api/auth/me"),
        ("POST", "/api/auth/logout"),
        ("POST", "/api/auth/step-up"),
        ("GET", "/api/billing/catalog"),
        ("GET", "/api/billing/status"),
        ("POST", "/api/billing/checkout"),
        ("POST", "/api/billing/portal"),
    }
)

# Entities carrying organization_id that the per-request session filters to the
# caller's org. Event tables (Snapshot/ChangeEvent/AIUsage/NotificationLog) are
# isolated by joining through a scoped Site/Recipient, so they need no column.
_ORG_SCOPED_ENTITIES = (
    Project,
    Site,
    Recipient,
    User,
    InteractionSecret,
    AIUsage,
    BillingCustomer,
    CheckoutAttempt,
    Subscription,
    InvoiceReference,
    EntitlementGrant,
    SupportAccessGrant,
    SiteCheckJob,
)


def _install_org_scope(session: AsyncSession) -> None:
    """Attach a row-level org filter to this request's session.

    The filter reads scope from ``session.info`` (set by ``get_current_user``
    after the user is loaded), so: unauthenticated/background sessions and
    superadmins are unfiltered, while a member's reads — including
    ``session.get()`` and lazy loads — are confined to their org. It is
    fail-closed: a member with no org matches ``organization_id IS NULL``, i.e.
    nothing, on the NOT NULL org tables."""

    @event.listens_for(session.sync_session, "do_orm_execute")
    def _scope(state: ORMExecuteState) -> None:
        if not state.is_select or state.execution_options.get("skip_org_filter"):
            return
        info = state.session.info
        if not info.get("org_scoped") or info.get("org_superadmin"):
            return
        org_id = info.get("org_id")
        for entity in _ORG_SCOPED_ENTITIES:
            state.statement = state.statement.options(
                with_loader_criteria(entity, entity.organization_id == org_id, include_aliases=True)
            )


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_database(request: Request) -> Database:
    return request.app.state.db  # type: ignore[no-any-return]


def get_runner(request: Request) -> SiteRunner:
    return request.app.state.runner  # type: ignore[no-any-return]


def get_scheduler(request: Request) -> MonitorScheduler:
    return request.app.state.scheduler  # type: ignore[no-any-return]


def get_maintenance(request: Request) -> MaintenanceMode:
    return request.app.state.maintenance  # type: ignore[no-any-return]


def get_picker(request: Request) -> PickerService:
    return request.app.state.picker  # type: ignore[no-any-return]


def get_secret_box(request: Request) -> SecretBox:
    return request.app.state.secret_box  # type: ignore[no-any-return]


def get_login_throttle(request: Request) -> LoginThrottle:
    return request.app.state.login_throttle  # type: ignore[no-any-return]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Finish the transaction before the response can advertise success.

    ``SessionDep`` uses function scope: FastAPI serializes the endpoint result,
    then finalizes this dependency before sending headers or response cookies.
    Explicitly committed operations and database restore opt out of the final
    commit via ``skip_final_commit``.
    """
    async with get_database(request).session() as session:
        _install_org_scope(session)
        try:
            yield session
            if not session.sync_session.info.get("skip_final_commit"):
                await session.commit()
        except Exception:
            await session.rollback()
            raise


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DatabaseDep = Annotated[Database, Depends(get_database)]
RunnerDep = Annotated[SiteRunner, Depends(get_runner)]
SchedulerDep = Annotated[MonitorScheduler, Depends(get_scheduler)]
MaintenanceDep = Annotated[MaintenanceMode, Depends(get_maintenance)]
PickerDep = Annotated[PickerService, Depends(get_picker)]
SecretBoxDep = Annotated[SecretBox, Depends(get_secret_box)]
SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]
LoginThrottleDep = Annotated[LoginThrottle, Depends(get_login_throttle)]


async def get_current_user(request: Request, session: SessionDep, settings: SettingsDep) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        claims = read_session(token, secret=settings.token_secrets)
    except SessionError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session") from exc
    # Loaded before the org scope is set, so any user resolves by id here.
    user = await session.get(User, claims.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account no longer exists")
    if (
        claims.token_version != user.token_version
        or claims.session_generation != user.session_generation
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session has been revoked")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is deactivated")
    endpoint = (request.method.upper(), request.url.path)
    mfa_enrollment_required = _mfa_enrollment_required(user, settings)
    if mfa_enrollment_required and endpoint not in _MFA_ENROLLMENT_ENDPOINTS:
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            "MFA enrollment required",
        )
    # A suspended organization locks out its members and admins (e.g. on a lapsed
    # subscription), but never the operator, who must still administer it. An
    # administrator who has not enrolled MFA retains only the enrollment surface
    # above; checking that policy first prevents a suspended tenant from making
    # enrollment impossible.
    if not user.is_superadmin and user.organization_id is not None:
        org = await session.get(Organization, user.organization_id)
        if (
            org is not None
            and not org.is_active
            and endpoint not in _BILLING_RECOVERY_ENDPOINTS
            and not (mfa_enrollment_required and endpoint in _MFA_ENROLLMENT_ENDPOINTS)
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This organization is suspended")
    await _apply_org_context(
        request,
        session,
        user,
        instance_scope_allowed=not mfa_enrollment_required,
    )
    request.state.confirmed_organization_id = _confirmed_organization_id(session)
    await _enforce_operator_support_access(request, session, user, settings)
    return user


async def _enforce_operator_support_access(
    request: Request,
    session: AsyncSession,
    user: User,
    settings: Settings,
) -> None:
    """Lock public tenant support access until a scoped break-glass grant.

    Local development preserves the ergonomic single-operator behavior. On an
    exposed instance, requests to other tenants must carry a short-lived grant
    bound to the operator, token version, and server-confirmed organization. An
    operator who is also their home workspace's administrator works there under
    ordinary organization scoping, without pretending to provide support.
    """
    if settings.is_local or not user.is_superadmin:
        return
    organization_id = session.sync_session.info.get("org_id")
    if organization_id is None:
        if not _is_instance_control_plane_request(request.url.path):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Enter an organization before accessing tenant-owned resources",
            )
        return
    if not operator_support_access_required(user, settings, int(organization_id)):
        return
    if _support_access_control_request(request):
        return
    claims = await current_support_access(
        request,
        session,
        user,
        settings,
        int(organization_id),
    )
    if claims is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Tenant support access is locked; request a time-limited audited grant",
        )
    request.state.support_access = claims
    if getattr(request.state, "support_access_audited", False):
        return
    request.state.support_access_audited = True
    record_audit_event(
        session,
        request,
        user,
        action="support.access_request",
        target_type="organization",
        target_id=organization_id,
        organization_id=int(organization_id),
        details={
            "method": request.method.upper(),
            "path": request.url.path,
            "grant_event_id": claims.grant_event_id,
        },
    )


def operator_support_access_required(user: User, settings: Settings, organization_id: int) -> bool:
    return (
        not settings.is_local
        and user.is_superadmin
        and not (user.is_admin and user.organization_id == organization_id)
    )


async def current_support_access(
    request: Request,
    session: AsyncSession,
    user: User,
    settings: Settings,
    organization_id: int,
) -> SupportAccessClaims | None:
    token = request.cookies.get(SUPPORT_ACCESS_COOKIE)
    if not token:
        return None
    try:
        claims = read_support_access_token(token, secret=settings.token_secrets)
    except SessionError:
        return None
    if (
        claims.user_id != user.id
        or claims.token_version != user.token_version
        or claims.session_generation != user.session_generation
        or claims.organization_id != organization_id
    ):
        return None
    grant_id = await session.scalar(
        select(SupportAccessGrant.id).where(
            SupportAccessGrant.operator_user_id == user.id,
            SupportAccessGrant.organization_id == organization_id,
            SupportAccessGrant.grant_event_id == claims.grant_event_id,
            SupportAccessGrant.active_marker.is_(True),
            SupportAccessGrant.revoked_at.is_(None),
            SupportAccessGrant.expires_at > datetime.now(UTC),
        )
    )
    return claims if grant_id is not None else None


def _support_access_control_request(request: Request) -> bool:
    path = request.url.path
    return path == "/api/support-access" or path.startswith("/api/auth/")


def _is_instance_control_plane_request(path: str) -> bool:
    if path in _INSTANCE_CONTROL_PLANE_EXACT_PATHS:
        return True
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in _INSTANCE_CONTROL_PLANE_PREFIXES
    )


def _mfa_enrollment_required(user: User, settings: Settings) -> bool:
    return not settings.is_local and (user.is_admin or user.is_superadmin) and not user.totp_enabled


async def _apply_org_context(
    request: Request,
    session: AsyncSession,
    user: User,
    *,
    instance_scope_allowed: bool = True,
) -> None:
    """Decide which organization this request reads from and writes to.

    A member or org-admin is always confined to their own organization. The
    operator (superadmin) defaults to an instance-wide view (sees every org, no
    single write target) but may "enter" one organization via the X-Acting-Org
    header — then they read and write that org exactly like its admin, while
    keeping their operator powers. ``write_org_id`` is the single source of truth
    for which org new resources belong to (None means "no org chosen yet")."""
    info = session.sync_session.info
    info["org_scoped"] = True
    if not user.is_superadmin or not instance_scope_allowed:
        if user.is_superadmin and (raw := request.headers.get(ACTING_ORG_HEADER)):
            # MFA enrollment endpoints may confirm the owner's home workspace,
            # but cannot enter an unrelated tenant or widen to instance scope.
            try:
                own_workspace = user.is_admin and int(raw) == user.organization_id
            except ValueError:
                own_workspace = False
            if not own_workspace:
                raise HTTPException(
                    status.HTTP_428_PRECONDITION_REQUIRED,
                    "MFA enrollment required",
                )
        info["org_superadmin"] = False
        info["org_id"] = user.organization_id
        info["write_org_id"] = user.organization_id
        return

    acting = await _acting_org(request, session)
    info["org_superadmin"] = acting is None  # exempt from the row filter only at instance level
    info["org_id"] = acting
    # New resources land in the entered org; with none entered they default to the
    # operator's own organization rather than failing.
    info["write_org_id"] = acting if acting is not None else user.organization_id


async def _acting_org(request: Request, session: AsyncSession) -> int | None:
    """The organization a superadmin has entered, or None for the instance view.
    A supplied context is fail-closed: malformed or stale ids must never widen an
    operator request back to the instance-wide scope."""
    raw = request.headers.get(ACTING_ORG_HEADER)
    if not raw:
        return None
    try:
        org_id = int(raw)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid acting organization") from None
    if org_id < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid acting organization")
    if await session.get(Organization, org_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Acting organization not found")
    return org_id


def _confirmed_organization_id(session: AsyncSession) -> int | None:
    """Return the canonical tenant scope established by ``_apply_org_context``."""
    info = session.sync_session.info
    if "org_id" not in info:
        raise RuntimeError("organization context has not been established")
    organization_id = info["org_id"]
    if organization_id is None:
        return None
    if isinstance(organization_id, bool) or not isinstance(organization_id, int):
        raise RuntimeError("organization context is not canonical")
    if organization_id < 1:
        raise RuntimeError("organization context is not canonical")
    return organization_id


async def optional_user(
    request: Request, session: SessionDep, settings: SettingsDep
) -> User | None:
    """The current user if a valid session cookie is present, else None — for
    endpoints that are public but personalise their response when signed in. Does
    not raise on a missing or stale session, and does not apply the org-scope
    filter (callers only read non-scoped settings)."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        claims = read_session(token, secret=settings.token_secrets)
    except SessionError:
        return None
    user = await session.get(User, claims.user_id)
    if (
        user is None
        or claims.token_version != user.token_version
        or claims.session_generation != user.session_generation
        or not user.is_active
    ):
        return None
    return user


async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    # Org-admin within their org, or the instance superadmin everywhere.
    if not (user.is_admin or user.is_superadmin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator privileges required")
    return user


async def require_superadmin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_superadmin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operator (superadmin) privileges required")
    return user


async def require_instance_superadmin(
    session: SessionDep,
    user: Annotated[User, Depends(require_superadmin)],
) -> User:
    """Require an operator in the unscoped, instance control-plane context."""
    info = session.sync_session.info
    if info.get("org_id") is not None or not info.get("org_superadmin"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Exit the active organization before managing instance resources",
        )
    return user


async def require_step_up(
    request: Request, user: Annotated[User, Depends(get_current_user)], settings: SettingsDep
) -> User:
    """Demand proof of a recent re-authentication. Responds 428 (distinct from a
    plain 403) so the client knows to prompt for the password again rather than
    treat it as a permanent denial."""
    detail = "Re-authentication required"
    token = request.cookies.get(STEP_UP_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, detail)
    try:
        claims = read_step_up_token(token, secret=settings.token_secrets)
    except SessionError as exc:
        raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, detail) from exc
    missing_scope = object()
    confirmed_organization_id = getattr(request.state, "confirmed_organization_id", missing_scope)
    if (
        confirmed_organization_id is missing_scope
        or claims.user_id != user.id
        or claims.token_version != user.token_version
        or claims.session_generation != user.session_generation
        or claims.organization_id != confirmed_organization_id
    ):
        raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, detail)
    return user


async def require_org_context(
    session: SessionDep, _: Annotated[User, Depends(get_current_user)]
) -> int:
    """The organization new resources are created in: the caller's own org, or
    the one the operator has entered. The operator must enter an org first."""
    write_org = session.sync_session.info.get("write_org_id")
    if write_org is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Enter an organization before creating anything in it"
        )
    return int(write_org)


async def require_explicit_org_context(
    session: SessionDep, user: Annotated[User, Depends(get_current_user)]
) -> int:
    """Resolve a tenant only when the operator explicitly entered it.

    Regular organization users are already server-confined to their home tenant.
    A superadmin's home organization is bootstrap metadata, not implicit consent to
    execute tenant control-plane operations against it.
    """
    organization_id = session.sync_session.info.get("org_id")
    if organization_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Enter an organization before accessing tenant billing",
        )
    if user.is_superadmin and session.sync_session.info.get("org_superadmin"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Enter an organization before accessing tenant billing",
        )
    return int(organization_id)


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalCurrentUser = Annotated[User | None, Depends(optional_user)]
AdminUser = Annotated[User, Depends(require_admin)]
SuperadminUser = Annotated[User, Depends(require_superadmin)]
InstanceSuperadminUser = Annotated[User, Depends(require_instance_superadmin)]
StepUpUser = Annotated[User, Depends(require_step_up)]
OrgContext = Annotated[int, Depends(require_org_context)]
ExplicitOrgContext = Annotated[int, Depends(require_explicit_org_context)]


def settings_store(session: SessionDep, box: SecretBoxDep, _: AdminUser) -> SettingsStore:
    # Settings scope follows the read scope (org_id), not the write target: the
    # operator at instance level (org_id None) edits the instance defaults, while
    # an org-admin — or operator who has entered an org — edits that org's layer.
    org_id = session.sync_session.info.get("org_id")
    return SettingsStore(session, box, org_id=org_id)


StoreDep = Annotated[SettingsStore, Depends(settings_store)]
