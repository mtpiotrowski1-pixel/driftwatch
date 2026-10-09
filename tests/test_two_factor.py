"""Unit tests for TOTP, recovery codes, and token purpose isolation."""

from __future__ import annotations

import pytest

from driftwatch.security import two_factor
from driftwatch.security.tokens import (
    PURPOSE_PENDING_TOTP,
    PURPOSE_STEP_UP,
    SessionError,
    issue_scoped_token,
    issue_session,
    issue_step_up_token,
    read_scoped_token,
    read_session,
    read_step_up_token,
)

# RFC 6238 Appendix B reference vector (SHA-1, ASCII secret "12345678901234567890").
_RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
_SESSION_GENERATION = "2f8d2a36-9de4-4b61-9f0e-0b5fe35b19cf"


def test_totp_matches_rfc6238_vector() -> None:
    assert two_factor.generate_code(_RFC_SECRET, at=59) == "287082"
    assert two_factor.verify(_RFC_SECRET, "287082", at=59, window=0) is True


def test_totp_rejects_wrong_and_malformed_codes() -> None:
    assert two_factor.verify(_RFC_SECRET, "000000", at=59, window=0) is False
    assert two_factor.verify(_RFC_SECRET, "28708", at=59) is False  # too short
    assert two_factor.verify(_RFC_SECRET, "abcdef", at=59) is False


def test_totp_tolerates_one_step_of_drift() -> None:
    code = two_factor.generate_code(_RFC_SECRET, at=59)
    assert two_factor.verify(_RFC_SECRET, code, at=59 + 30, window=1) is True
    assert two_factor.verify(_RFC_SECRET, code, at=59 + 90, window=1) is False


def test_generated_secret_round_trips() -> None:
    secret = two_factor.generate_secret()
    code = two_factor.generate_code(secret, at=1000)
    assert two_factor.verify(secret, code, at=1000, window=0) is True


def test_recovery_codes_are_unique_and_hash_ignores_formatting() -> None:
    codes = two_factor.generate_recovery_codes()
    assert len(codes) == len(set(codes)) == 10
    code = codes[0]
    assert two_factor.hash_recovery_code(code) == two_factor.hash_recovery_code(code.upper())
    assert two_factor.hash_recovery_code(code) == two_factor.hash_recovery_code(
        code.replace("-", " ")
    )


def test_session_token_rejects_purpose_tokens() -> None:
    secret = "a-sufficiently-long-test-signing-secret-key"
    pending = issue_scoped_token(
        7,
        secret=secret,
        purpose=PURPOSE_PENDING_TOTP,
        ttl_seconds=60,
        session_generation=_SESSION_GENERATION,
    )
    with pytest.raises(SessionError):
        read_session(pending, secret=secret)


def test_scoped_token_rejects_wrong_purpose_and_session() -> None:
    secret = "a-sufficiently-long-test-signing-secret-key"
    step_up = issue_scoped_token(
        7,
        secret=secret,
        purpose=PURPOSE_STEP_UP,
        ttl_seconds=60,
        session_generation=_SESSION_GENERATION,
    )
    with pytest.raises(SessionError):
        read_scoped_token(step_up, secret=secret, purpose=PURPOSE_PENDING_TOTP)

    session = issue_session(7, secret=secret, ttl_hours=1, session_generation=_SESSION_GENERATION)
    with pytest.raises(SessionError):
        read_scoped_token(session, secret=secret, purpose=PURPOSE_STEP_UP)
    assert read_session(session, secret=secret).user_id == 7


def test_step_up_token_requires_an_explicit_canonical_organization_scope() -> None:
    old_secret = "old-step-up-key-padding-to-thirty-two-bytes"
    current_secret = "new-step-up-key-padding-to-thirty-two-bytes"
    tenant_token = issue_step_up_token(
        7,
        organization_id=42,
        secret=old_secret,
        ttl_seconds=60,
        token_version=3,
        session_generation=_SESSION_GENERATION,
    )

    tenant_claims = read_step_up_token(
        tenant_token,
        secret=(current_secret, old_secret),
    )
    assert tenant_claims.user_id == 7
    assert tenant_claims.token_version == 3
    assert tenant_claims.session_generation == _SESSION_GENERATION
    assert tenant_claims.organization_id == 42

    instance_token = issue_step_up_token(
        7,
        organization_id=None,
        secret=current_secret,
        ttl_seconds=60,
        session_generation=_SESSION_GENERATION,
    )
    assert read_step_up_token(instance_token, secret=current_secret).organization_id is None

    legacy_unscoped = issue_scoped_token(
        7,
        secret=current_secret,
        purpose=PURPOSE_STEP_UP,
        ttl_seconds=60,
        session_generation=_SESSION_GENERATION,
    )
    with pytest.raises(SessionError):
        read_step_up_token(legacy_unscoped, secret=current_secret)

    with pytest.raises(ValueError):
        issue_step_up_token(
            7,
            organization_id=0,
            secret=current_secret,
            ttl_seconds=60,
            session_generation=_SESSION_GENERATION,
        )
