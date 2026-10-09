"""Stateless tokens carried in httpOnly cookies.

A token is a short JWT signed with the application secret; there is no
server-side session store. Each encodes the user id, a token version, and an
expiry. The version lets a password change invalidate every issued token at
once — the request layer compares it to the user's current version.

Besides the full session token there are short-lived *purpose-scoped* tokens
(``pur`` claim) for intermediate states: a password-verified login still
awaiting its TOTP code, and a fresh re-authentication granting a brief window
to perform a destructive action. A session token never carries a purpose, and a
purpose token can never be read as a session — the two are not interchangeable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

_ALGORITHM = "HS256"

# Purposes for short-lived intermediate tokens.
PURPOSE_PENDING_TOTP = "pending_totp"
PURPOSE_STEP_UP = "step_up"
PURPOSE_PASSWORD_RESET = "password_reset"
PURPOSE_SUPPORT_ACCESS = "support_access"


class SessionError(Exception):
    """Raised when a token is missing, malformed, expired, or the wrong kind."""


@dataclass(frozen=True, slots=True)
class SessionClaims:
    user_id: int
    token_version: int
    session_generation: str


@dataclass(frozen=True, slots=True)
class PendingLoginClaims(SessionClaims):
    nonce: str


@dataclass(frozen=True, slots=True)
class StepUpClaims:
    user_id: int
    token_version: int
    session_generation: str
    organization_id: int | None


@dataclass(frozen=True, slots=True)
class SupportAccessClaims:
    user_id: int
    token_version: int
    session_generation: str
    organization_id: int
    grant_event_id: int
    expires_at: datetime


def issue_session(
    user_id: int,
    *,
    secret: str,
    ttl_hours: int,
    session_generation: str,
    token_version: int = 0,
) -> str:
    return _encode(
        user_id,
        secret=secret,
        ttl_seconds=ttl_hours * 3600,
        token_version=token_version,
        session_generation=session_generation,
    )


def read_session(token: str, *, secret: str | Sequence[str]) -> SessionClaims:
    payload = _decode(token, secret=secret)
    if "pur" in payload:
        # A purpose-scoped token (pending-TOTP / step-up) must never authenticate.
        raise SessionError("not a session token")
    return _claims(payload)


def issue_scoped_token(
    user_id: int,
    *,
    secret: str,
    purpose: str,
    ttl_seconds: int,
    session_generation: str,
    token_version: int = 0,
    issued_at: datetime | None = None,
    nonce: str | None = None,
) -> str:
    return _encode(
        user_id,
        secret=secret,
        ttl_seconds=ttl_seconds,
        token_version=token_version,
        session_generation=session_generation,
        purpose=purpose,
        issued_at=issued_at,
        extra_claims={"nonce": nonce} if nonce is not None else None,
    )


def read_pending_login(token: str, *, secret: str | Sequence[str]) -> PendingLoginClaims:
    payload = _decode(token, secret=secret)
    if payload.get("pur") != PURPOSE_PENDING_TOTP:
        raise SessionError("wrong token purpose")
    base = _claims(payload)
    try:
        nonce = str(UUID(str(payload["nonce"])))
    except (KeyError, ValueError, TypeError) as exc:
        raise SessionError("invalid login challenge") from exc
    return PendingLoginClaims(base.user_id, base.token_version, base.session_generation, nonce)


def read_scoped_token(token: str, *, secret: str | Sequence[str], purpose: str) -> SessionClaims:
    payload = _decode(token, secret=secret)
    if payload.get("pur") != purpose:
        raise SessionError("wrong token purpose")
    return _claims(payload)


def issue_step_up_token(
    user_id: int,
    *,
    organization_id: int | None,
    secret: str,
    ttl_seconds: int,
    session_generation: str,
    token_version: int = 0,
) -> str:
    if organization_id is not None and (
        isinstance(organization_id, bool)
        or not isinstance(organization_id, int)
        or organization_id < 1
    ):
        raise ValueError("invalid step-up organization scope")
    return _encode(
        user_id,
        secret=secret,
        ttl_seconds=ttl_seconds,
        token_version=token_version,
        session_generation=session_generation,
        purpose=PURPOSE_STEP_UP,
        # JSON null is an explicit instance scope. Omitting the claim would make
        # legacy, unscoped proofs ambiguous and is therefore rejected on read.
        extra_claims={"org": organization_id},
    )


def read_step_up_token(token: str, *, secret: str | Sequence[str]) -> StepUpClaims:
    payload = _decode(token, secret=secret)
    if payload.get("pur") != PURPOSE_STEP_UP:
        raise SessionError("wrong token purpose")
    base = _claims(payload)
    try:
        raw_organization_id = payload["org"]
    except KeyError as exc:
        raise SessionError("missing step-up organization scope") from exc
    if raw_organization_id is None:
        organization_id = None
    elif (
        isinstance(raw_organization_id, int)
        and not isinstance(raw_organization_id, bool)
        and raw_organization_id >= 1
    ):
        organization_id = raw_organization_id
    else:
        raise SessionError("invalid step-up organization scope")
    return StepUpClaims(
        user_id=base.user_id,
        token_version=base.token_version,
        session_generation=base.session_generation,
        organization_id=organization_id,
    )


def issue_support_access_token(
    user_id: int,
    *,
    organization_id: int,
    grant_event_id: int,
    secret: str,
    ttl_seconds: int,
    session_generation: str,
    token_version: int = 0,
) -> str:
    return _encode(
        user_id,
        secret=secret,
        ttl_seconds=ttl_seconds,
        token_version=token_version,
        session_generation=session_generation,
        purpose=PURPOSE_SUPPORT_ACCESS,
        extra_claims={"org": organization_id, "grant": grant_event_id},
    )


def read_support_access_token(token: str, *, secret: str | Sequence[str]) -> SupportAccessClaims:
    payload = _decode(token, secret=secret)
    if payload.get("pur") != PURPOSE_SUPPORT_ACCESS:
        raise SessionError("wrong token purpose")
    base = _claims(payload)
    try:
        organization_id = int(str(payload["org"]))
        grant_event_id = int(str(payload["grant"]))
        expires_at = datetime.fromtimestamp(int(str(payload["exp"])), tz=UTC)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise SessionError(str(exc)) from exc
    if organization_id < 1 or grant_event_id < 1:
        raise SessionError("invalid support access scope")
    return SupportAccessClaims(
        user_id=base.user_id,
        token_version=base.token_version,
        session_generation=base.session_generation,
        organization_id=organization_id,
        grant_event_id=grant_event_id,
        expires_at=expires_at,
    )


def _encode(
    user_id: int,
    *,
    secret: str,
    ttl_seconds: int,
    token_version: int,
    session_generation: str,
    purpose: str | None = None,
    extra_claims: Mapping[str, object] | None = None,
    issued_at: datetime | None = None,
) -> str:
    now = issued_at or datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": str(user_id),
        "ver": token_version,
        "gen": session_generation,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    if purpose is not None:
        payload["pur"] = purpose
    if extra_claims:
        if payload.keys() & extra_claims.keys():
            raise ValueError("extra claims cannot replace reserved token claims")
        payload.update(extra_claims)
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def _decode(token: str, *, secret: str | Sequence[str]) -> dict[str, object]:
    keys = (secret,) if isinstance(secret, str) else tuple(secret)
    last_error: jwt.InvalidTokenError | None = None
    for key in keys:
        try:
            return jwt.decode(
                token,
                key,
                algorithms=[_ALGORITHM],
                options={"require": ["sub", "ver", "gen", "iat", "exp"]},
            )
        except jwt.InvalidTokenError as exc:
            last_error = exc
    raise SessionError(str(last_error or "no token verification keys configured")) from last_error


def _claims(payload: dict[str, object]) -> SessionClaims:
    try:
        sub = payload["sub"]
        ver = payload["ver"]
        raw_generation = str(payload["gen"])
        session_generation = str(UUID(raw_generation))
        if session_generation != raw_generation:
            raise ValueError("session generation is not canonical")
        return SessionClaims(
            user_id=int(str(sub)),
            token_version=int(str(ver)),
            session_generation=session_generation,
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise SessionError(str(exc)) from exc
