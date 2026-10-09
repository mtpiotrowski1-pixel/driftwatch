"""Authentication: login (optionally two-factor), logout, registration, the
current user, and TOTP enrollment.

Sessions are stateless JWTs in an httpOnly, SameSite=Lax cookie. When an account
has TOTP enabled the password step yields only a short-lived pending-2FA cookie;
the real session is issued by ``/login/totp`` once the code checks out. On a
fresh local installation the first account becomes the instance operator. An
explicit deployment opt-in permits that claim behind a non-loopback bind. The
claim persists independently of account deletion, and later registration is
closed unless the owner explicitly enables it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import segno
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.account_mail import enqueue_password_reset
from driftwatch.api.deps import (
    PENDING_TOTP_COOKIE,
    SESSION_COOKIE,
    STEP_UP_COOKIE,
    STEP_UP_TTL_SECONDS,
    SUPPORT_ACCESS_COOKIE,
    CurrentUser,
    LoginThrottleDep,
    SecretBoxDep,
    SessionDep,
    SettingsDep,
    StepUpUser,
    _confirmed_organization_id,
    _mfa_enrollment_required,
)
from driftwatch.audit import record_audit_event
from driftwatch.bootstrap import claim_initial_admin, initial_admin_signup_available
from driftwatch.models import Organization, User, project_editors, site_editors
from driftwatch.quota import reserve_member_slot
from driftwatch.schemas import (
    AuthCapabilitiesOut,
    ChangePasswordRequest,
    LoginRequest,
    LoginResult,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    StepUpRequest,
    TotpEnableRequest,
    TotpLoginRequest,
    TotpSetupOut,
    UserOut,
)
from driftwatch.security import two_factor
from driftwatch.security.crypto import SecretBox
from driftwatch.security.passwords import (
    ahash_password,
    averify_password,
    hash_password,
    needs_rehash,
)
from driftwatch.security.throttle import LoginThrottle
from driftwatch.security.tokens import (
    PURPOSE_PASSWORD_RESET,
    PURPOSE_PENDING_TOTP,
    PendingLoginClaims,
    SessionError,
    issue_scoped_token,
    issue_session,
    issue_step_up_token,
    read_pending_login,
    read_scoped_token,
)
from driftwatch.services import ensure_default_organization
from driftwatch.settings_store import SettingsStore

router = APIRouter(prefix="/api/auth", tags=["auth"])

# A real Argon2 hash verified against on the unknown-email path so a login for a
# nonexistent account costs the same as one for a real account — no timing oracle.
_DUMMY_PASSWORD_HASH = hash_password("driftwatch-timing-equalizer")
_PENDING_TOTP_TTL_SECONDS = 300
# Login is throttled on two axes: per source IP (catches one machine guessing)
# and per email address (catches a distributed spray against one account from
# many IPs). Reserve the higher per-address budget before expensive verification.
# The bounded delay can also affect the owner during a spray; completing
# password recovery clears it without allowing more unauthenticated guesses.
_LOGIN_EMAIL_MAX = 20
# New self-serve organizations one IP may create before it must wait.
_SIGNUP_IP_MAX = 5
# Duplicate-email registrations one IP may attempt before it must wait. A 409
# reveals that an address is taken, so without its own ceiling the endpoint is an
# unthrottled account-enumeration oracle. Kept on a dedicated key so honest
# re-registration never spends — and so never locks the IP out of — the login budget.
_REGISTER_PROBE_MAX = 10
# Public registration is deliberately non-entitling until a verified payment
# flow exists. Organization's NULL caps mean unlimited, so relying on model
# defaults here would fail open.
_PUBLIC_SIGNUP_PLAN = "free"
_PUBLIC_SIGNUP_MAX_SITES = 1
_PUBLIC_SIGNUP_MAX_MEMBERS = 1
_PUBLIC_SIGNUP_MONTHLY_AI_CHECK_LIMIT = 0


@router.post("/login", response_model=LoginResult)
async def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    throttle: LoginThrottleDep,
) -> LoginResult:
    email = credentials.email.lower()
    ip_key = _client_key(request)
    email_key = f"login-email:{email}"
    await _reject_if_throttled(throttle, ip_key)
    retry_after = await throttle.consume(email_key, max_actions=_LOGIN_EMAIL_MAX)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many attempts. Please wait or use password recovery.",
            headers={"Retry-After": str(int(retry_after))},
        )
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    # Always run exactly one Argon2 verification, whether or not the email exists.
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_valid = await averify_password(credentials.password, password_hash)
    if user is None or not password_valid:
        await throttle.record_failure(ip_key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is deactivated")

    await throttle.reset(ip_key)
    await throttle.reset(email_key)
    if needs_rehash(user.password_hash):
        user.password_hash = await ahash_password(credentials.password)

    # With 2FA on, the password is not enough: hand back only a short-lived
    # pending cookie and require the code via /login/totp before a real session.
    if user.totp_enabled:
        user.pending_totp_nonce = str(uuid4())
        _set_cookie(
            response,
            PENDING_TOTP_COOKIE,
            issue_scoped_token(
                user.id,
                secret=settings.token_secret,
                purpose=PURPOSE_PENDING_TOTP,
                ttl_seconds=_PENDING_TOTP_TTL_SECONDS,
                token_version=user.token_version,
                session_generation=user.session_generation,
                nonce=user.pending_totp_nonce,
            ),
            settings,
            max_age=_PENDING_TOTP_TTL_SECONDS,
        )
        return LoginResult(totp_required=True)

    _complete_login(response, user, settings)
    result = await _user_out(session, user, settings)
    return LoginResult(user=result)


@router.post("/login/totp", response_model=UserOut)
async def login_totp(
    payload: TotpLoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    box: SecretBoxDep,
    throttle: LoginThrottleDep,
) -> UserOut:
    token = request.cookies.get(PENDING_TOTP_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No login in progress")
    try:
        claims = read_pending_login(token, secret=settings.token_secrets)
    except SessionError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login session expired") from exc

    # Throttle the code step per account so the 6-digit space can't be hammered.
    throttle_key = f"totp:{claims.user_id}"
    await _reject_if_throttled(throttle, throttle_key)
    user = (
        await session.execute(select(User).where(User.id == claims.user_id).with_for_update())
    ).scalar_one_or_none()
    if (
        user is None
        or not user.totp_enabled
        or claims.token_version != user.token_version
        or claims.session_generation != user.session_generation
        or claims.nonce != user.pending_totp_nonce
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login session expired")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is deactivated")
    recovery_codes_before = len(user.recovery_code_hashes)
    if not await _consume_login_factor(session, user, payload.code, box, claims):
        await throttle.record_failure(throttle_key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid code")

    await throttle.reset(throttle_key)
    response.delete_cookie(PENDING_TOTP_COOKIE, path="/")
    _complete_login(response, user, settings)
    if len(user.recovery_code_hashes) < recovery_codes_before:
        _record_account_security_event(
            session,
            request,
            user,
            action="account.recovery_code_used",
        )
    return await _user_out(session, user, settings)


@router.get("/capabilities", response_model=AuthCapabilitiesOut)
async def auth_capabilities(
    response: Response, settings: SettingsDep, session: SessionDep
) -> AuthCapabilitiesOut:
    """Expose only the public auth switches needed to render the entry flow."""
    # The first signup immediately changes this capability. Do not keep a stale
    # registration button in a browser or shared proxy after ownership is claimed.
    response.headers["Cache-Control"] = "no-store"
    initial_setup_required = (
        settings.initial_admin_signup_allowed and await initial_admin_signup_available(session)
    )
    return AuthCapabilitiesOut(
        registration_enabled=settings.public_registration_enabled or initial_setup_required,
        initial_setup_required=initial_setup_required,
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    throttle: LoginThrottleDep,
) -> UserOut:
    key = _client_key(request)
    await _reject_if_throttled(throttle, key)
    # Claim before looking up accounts. This is a database write in the same
    # transaction as account creation, not a racy count-then-insert check.
    first_account = (
        await claim_initial_admin(session) if settings.initial_admin_signup_allowed else False
    )
    if not first_account and not settings.public_registration_enabled:
        # Fail before any account lookup so the closed endpoint cannot be used
        # as an email-existence oracle.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Public registration is disabled")
    email = payload.email.lower()
    exists = (
        await session.execute(select(User.id).where(User.email == email))
    ).scalar_one_or_none()
    if exists is not None:
        # A duplicate email is not a credential guess, so it must not consume the
        # shared login budget — but the 409 it returns reveals the address is
        # taken, so it gets its own per-IP ceiling to stop bulk enumeration.
        probe_key = f"register-exists:{key}"
        await throttle.record_failure(probe_key)
        await _reject_if_throttled(throttle, probe_key, max_failures=_REGISTER_PROBE_MAX)
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    # Public deploys are multi-tenant: every non-bootstrap account gets its OWN
    # isolated organization, so a sign-up can never land inside the operator's
    # seeded org and read its data. The shared "join the default org" path is kept
    # only for a local single-tenant/dev install.
    self_serve = not first_account and (
        payload.organization_name is not None or not settings.is_local
    )
    if self_serve:
        user = await _self_serve_signup(session, throttle, key, payload, email)
    else:
        # Bootstrap operator, or a local member of the shared default org.
        org = await ensure_default_organization(
            session,
            (payload.organization_name if first_account else None) or settings.default_org_name,
        )
        if not first_account:
            await reserve_member_slot(session, org.id)
        user = User(
            email=email,
            name=payload.name,
            password_hash=await ahash_password(payload.password),
            organization_id=org.id,
            is_superadmin=first_account,
            is_admin=first_account,
        )
        session.add(user)
    await session.flush()
    user.last_login_at = datetime.now(UTC)
    result = await _user_out(session, user, settings)
    # Bootstrap owns its transaction: finalize the claim and account together
    # before constructing the new session credential.
    await session.commit()
    session.sync_session.info["skip_final_commit"] = True
    _set_session_cookie(response, user, settings)
    return result


async def _self_serve_signup(
    session: SessionDep,
    throttle: LoginThrottle,
    ip_key: str,
    payload: RegisterRequest,
    email: str,
) -> User:
    """Create a new, isolated organization for a public sign-up and make this
    account its admin (never the instance operator). Rate-limited per IP so the
    endpoint can't be used to mass-create tenants."""
    await _reject_if_throttled(throttle, f"signup-ip:{ip_key}", max_failures=_SIGNUP_IP_MAX)
    await throttle.record_failure(f"signup-ip:{ip_key}")  # each creation counts toward the cap

    org = Organization(
        name=payload.organization_name or email,
        plan=_PUBLIC_SIGNUP_PLAN,
        plan_id=None,
        max_sites=_PUBLIC_SIGNUP_MAX_SITES,
        max_members=_PUBLIC_SIGNUP_MAX_MEMBERS,
        monthly_ai_check_limit=_PUBLIC_SIGNUP_MONTHLY_AI_CHECK_LIMIT,
    )
    session.add(org)
    await session.flush()
    await reserve_member_slot(session, org.id)

    user = User(
        email=email,
        name=payload.name,
        password_hash=await ahash_password(payload.password),
        organization_id=org.id,
        is_admin=True,
        is_superadmin=False,
    )
    session.add(user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(PENDING_TOTP_COOKIE, path="/")
    response.delete_cookie(STEP_UP_COOKIE, path="/")
    response.delete_cookie(SUPPORT_ACCESS_COOKIE, path="/api")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> UserOut:
    result = await _user_out(session, user, settings)
    acting_org_id = session.sync_session.info.get("org_id") if user.is_superadmin else None
    if acting_org_id is not None:
        organization = await session.get(Organization, int(acting_org_id))
        # _acting_org already validated this row. Keep the defensive branch so a
        # concurrent deletion cannot produce a client-side phantom context.
        if organization is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Acting organization not found")
        result.acting_organization_id = organization.id
        result.acting_organization_name = organization.name
    return result


async def _user_out(session: SessionDep, user: User, settings: SettingsDep) -> UserOut:
    """Build the auth contract with deployment and tenant state from the server."""
    result = UserOut.model_validate(user)
    result.project_ids = list(
        await session.scalars(
            select(project_editors.c.project_id).where(project_editors.c.user_id == user.id)
        )
    )
    result.site_ids = list(
        await session.scalars(
            select(site_editors.c.site_id).where(site_editors.c.user_id == user.id)
        )
    )
    result.mfa_enrollment_required = _mfa_enrollment_required(user, settings)
    if not user.is_superadmin and user.organization_id is not None:
        organization = await session.get(Organization, user.organization_id)
        result.organization_suspended = organization is not None and not organization.is_active
    return result


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    user: CurrentUser,
    settings: SettingsDep,
    throttle: LoginThrottleDep,
) -> None:
    # Throttle per-account so a hijacked session can't brute-force the current
    # password to pivot into a permanent takeover.
    key = f"chpw:{user.id}"
    await _reject_if_throttled(throttle, key)
    if not await averify_password(payload.current_password, user.password_hash):
        await throttle.record_failure(key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    await throttle.reset(key)
    user.password_hash = await ahash_password(payload.new_password)
    # Invalidate every other session, then re-issue this one so the caller stays in.
    user.token_version += 1
    _set_session_cookie(response, user, settings)
    _record_account_security_event(
        session,
        request,
        user,
        action="account.password_changed",
    )


@router.post("/request-password-reset", status_code=status.HTTP_204_NO_CONTENT)
async def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    throttle: LoginThrottleDep,
) -> None:
    """Email a password-reset link. Always returns 204 whether or not the address
    has an account, so it cannot be used to discover who is registered. Known and
    unknown addresses take the same durable enqueue path; target resolution and
    token generation happen only in the delivery worker."""
    email = payload.email.lower()
    for key in (f"reset-ip:{_client_key(request)}", f"reset-addr:{email}"):
        await _reject_if_throttled(throttle, key)
        await throttle.record_failure(key)

    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    await enqueue_password_reset(
        session,
        requested_email=email,
        user=user,
        secret=settings.token_secret,
        now=datetime.now(UTC),
    )


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: PasswordResetConfirm,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    throttle: LoginThrottleDep,
) -> None:
    """Set a new password from a valid reset token. Consuming it bumps the token
    version, which makes the link single-use and signs out every existing
    session — so a leaked or already-used link cannot be replayed."""
    key = f"reset-confirm:{_client_key(request)}"
    await _reject_if_throttled(throttle, key)
    invalid = HTTPException(
        status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired"
    )
    try:
        claims = read_scoped_token(
            payload.token, secret=settings.token_secrets, purpose=PURPOSE_PASSWORD_RESET
        )
    except SessionError:
        await throttle.record_failure(key)
        raise invalid from None
    user = (
        await session.execute(select(User).where(User.id == claims.user_id).with_for_update())
    ).scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or claims.token_version != user.token_version
        or claims.session_generation != user.session_generation
    ):
        await throttle.record_failure(key)
        raise invalid
    new_hash = await ahash_password(payload.new_password)
    consumed = await session.scalar(
        update(User)
        .where(
            User.id == claims.user_id,
            User.is_active.is_(True),
            User.token_version == claims.token_version,
            User.session_generation == claims.session_generation,
        )
        .values(
            password_hash=new_hash,
            token_version=User.token_version + 1,
            pending_totp_nonce=None,
        )
        .returning(User.id)
        .execution_options(synchronize_session=False)
    )
    if consumed is None:
        await throttle.record_failure(key)
        raise invalid
    await session.refresh(user)
    await throttle.reset(f"login-email:{user.email.lower()}")
    _record_account_security_event(
        session,
        request,
        user,
        action="account.password_reset",
    )


@router.post("/totp/setup", response_model=TotpSetupOut)
async def totp_setup(user: StepUpUser, session: SessionDep, box: SecretBoxDep) -> TotpSetupOut:
    """Begin enrollment: generate a fresh secret (stored encrypted, not yet
    active) and return it as a scannable QR plus its text form for manual entry."""
    if user.totp_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Two-factor authentication is already enabled"
        )
    secret = two_factor.generate_secret()
    user.totp_secret = box.encrypt(secret)
    user.totp_last_login_counter = None
    user.pending_totp_nonce = None
    # The issuer is the configured brand (org override else instance default),
    # shown in the authenticator app. Changing the brand later only affects
    # newly enrolled authenticators — existing entries keep their label.
    store = SettingsStore(session, box, org_id=user.organization_id)
    uri = two_factor.provisioning_uri(secret, account=user.email, issuer=await store.brand_name())
    return TotpSetupOut(
        secret=secret, otpauth_uri=uri, qr_svg_data_uri=segno.make(uri).svg_data_uri()
    )


@router.post("/totp/enable", response_model=dict[str, list[str]])
async def totp_enable(
    payload: TotpEnableRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    user: StepUpUser,
    settings: SettingsDep,
    box: SecretBoxDep,
    throttle: LoginThrottleDep,
) -> dict[str, list[str]]:
    """Confirm enrollment with a code from the app, then return one-time recovery
    codes (shown once — they are stored only as hashes)."""
    if user.totp_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Two-factor authentication is already enabled"
        )
    key = f"totp-enable:{user.id}"
    await _reject_if_throttled(throttle, key)
    secret = _decrypt_totp_secret(user, box)
    if secret is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Start setup before enabling")
    if not two_factor.verify(secret, payload.code):
        await throttle.record_failure(key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid code")
    await throttle.reset(key)
    codes = two_factor.generate_recovery_codes()
    user.recovery_code_hashes = [two_factor.hash_recovery_code(code) for code in codes]
    user.totp_enabled = True
    # Enrollment changes the account's authentication boundary. Revoke every
    # pre-enrollment token, then keep only this freshly authenticated browser
    # signed in with the new token generation.
    user.token_version += 1
    _record_account_security_event(
        session,
        request,
        user,
        action="account.totp_enabled",
    )
    # A follow-up /me can arrive as soon as the response headers are sent.
    # Persist the new factor and token generation before issuing its session.
    await session.commit()
    session.sync_session.info["skip_final_commit"] = True
    _set_session_cookie(response, user, settings)
    response.delete_cookie(STEP_UP_COOKIE, path="/")
    return {"recovery_codes": codes}


@router.post("/totp/disable", status_code=status.HTTP_204_NO_CONTENT)
async def totp_disable(
    request: Request,
    response: Response,
    session: SessionDep,
    user: StepUpUser,
    settings: SettingsDep,
) -> None:
    """Turn off 2FA after a fresh password and current-TOTP step-up."""
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_last_login_counter = None
    user.pending_totp_nonce = None
    user.recovery_code_hashes = []
    user.token_version += 1
    _set_session_cookie(response, user, settings)
    response.delete_cookie(STEP_UP_COOKIE, path="/")
    _record_account_security_event(
        session,
        request,
        user,
        action="account.totp_disabled",
    )


@router.post("/step-up", status_code=status.HTTP_204_NO_CONTENT)
async def step_up(
    payload: StepUpRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    user: CurrentUser,
    settings: SettingsDep,
    box: SecretBoxDep,
    throttle: LoginThrottleDep,
) -> None:
    """Re-authenticate to unlock the most destructive actions for a few minutes.

    Even a live session must prove the password again (and a TOTP code when 2FA
    is on) before downloading the full backup or deleting an organization, so a
    hijacked session cannot trigger them with a single click."""
    key = f"step-up:{user.id}:{_client_key(request)}"
    await _reject_if_throttled(throttle, key)
    if not await averify_password(payload.password, user.password_hash):
        await throttle.record_failure(key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password is incorrect")
    if user.totp_enabled:
        if not payload.totp_code:
            await throttle.record_failure(key)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Authentication code required")
        if not _verify_totp(user, payload.totp_code, box):
            await throttle.record_failure(key)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid code")
    await throttle.reset(key)
    organization_id = _confirmed_organization_id(session)
    token = issue_step_up_token(
        user.id,
        organization_id=organization_id,
        secret=settings.token_secret,
        ttl_seconds=STEP_UP_TTL_SECONDS,
        token_version=user.token_version,
        session_generation=user.session_generation,
    )
    _set_cookie(response, STEP_UP_COOKIE, token, settings, max_age=STEP_UP_TTL_SECONDS)


def _verify_totp(user: User, code: str, box: SecretBox) -> bool:
    """Check a live authenticator code only — recovery codes are not spent on a
    routine re-authentication."""
    secret = _decrypt_totp_secret(user, box)
    return secret is not None and two_factor.verify(secret, code)


async def _consume_login_factor(
    session: AsyncSession, user: User, code: str, box: SecretBox, claims: PendingLoginClaims
) -> bool:
    """Consume the challenge and factor in one conditional database write.

    SELECT FOR UPDATE does not lock rows on SQLite. This compare-and-set also
    fences parallel requests there, and across API processes on PostgreSQL.
    """
    secret = _decrypt_totp_secret(user, box)
    counter = two_factor.matching_counter(secret, code) if secret is not None else None
    statement = update(User).where(
        User.id == user.id,
        User.is_active.is_(True),
        User.totp_enabled.is_(True),
        User.token_version == claims.token_version,
        User.session_generation == claims.session_generation,
        User.pending_totp_nonce == claims.nonce,
    )
    if counter is not None:
        statement = statement.where(
            or_(User.totp_last_login_counter.is_(None), User.totp_last_login_counter < counter)
        ).values(totp_last_login_counter=counter, pending_totp_nonce=None)
    else:
        used = two_factor.hash_recovery_code(code)
        if used not in user.recovery_code_hashes:
            return False
        statement = statement.values(
            recovery_code_hashes=[h for h in user.recovery_code_hashes if h != used],
            pending_totp_nonce=None,
        )
    consumed = await session.scalar(
        statement.returning(User.id).execution_options(synchronize_session=False)
    )
    if consumed is None:
        return False
    await session.refresh(user)
    return True


def _decrypt_totp_secret(user: User, box: SecretBox) -> str | None:
    if not user.totp_secret:
        return None
    secret = box.decrypt(user.totp_secret)
    rotated = box.rotate(user.totp_secret)
    if secret is not None and rotated is not None and rotated != user.totp_secret:
        user.totp_secret = rotated
    return secret


def _complete_login(response: Response, user: User, settings: SettingsDep) -> None:
    user.last_login_at = datetime.now(UTC)
    _set_session_cookie(response, user, settings)


def _record_account_security_event(
    session: SessionDep,
    request: Request,
    user: User,
    *,
    action: str,
) -> None:
    record_audit_event(
        session,
        request,
        user,
        action=action,
        target_type="account",
        target_id=user.id,
        target_label=user.email,
        organization_id=None if user.is_superadmin else user.organization_id,
    )


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _reject_if_throttled(
    throttle: LoginThrottle, key: str, *, max_failures: int | None = None
) -> None:
    retry_after = await throttle.retry_after(key, max_failures=max_failures)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many attempts. Please wait and try again.",
            headers={"Retry-After": str(int(retry_after))},
        )


def _set_session_cookie(response: Response, user: User, settings: SettingsDep) -> None:
    token = issue_session(
        user.id,
        secret=settings.token_secret,
        ttl_hours=settings.session_ttl_hours,
        token_version=user.token_version,
        session_generation=user.session_generation,
    )
    max_age = settings.session_ttl_hours * 3600
    _set_cookie(response, SESSION_COOKIE, token, settings, max_age=max_age)


def _set_cookie(
    response: Response, name: str, value: str, settings: SettingsDep, *, max_age: int
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=not settings.is_local,
        path="/",
    )
