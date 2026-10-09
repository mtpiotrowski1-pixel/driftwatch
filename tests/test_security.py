"""Tests for password hashing, session tokens, and secret encryption."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import time

import jwt
import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from driftwatch.config import INSECURE_SECRET_KEY, Settings
from driftwatch.security.crypto import SecretBox
from driftwatch.security.passwords import hash_password, verify_password
from driftwatch.security.throttle import _SWEEP_THRESHOLD, LoginThrottle
from driftwatch.security.tokens import SessionError, issue_session, read_session

_SESSION_GENERATION = "2f8d2a36-9de4-4b61-9f0e-0b5fe35b19cf"


async def test_login_throttle_sweeps_aged_out_keys() -> None:
    throttle = LoginThrottle(window_seconds=0.05)
    for index in range(_SWEEP_THRESHOLD + 50):
        await throttle.record_failure(f"ip-{index}")
    await asyncio.sleep(0.1)  # let every recorded failure age out of the window
    await throttle.record_failure("fresh")  # size-gated sweep drops the stale keys
    assert len(throttle._failures) <= 2


async def test_login_throttle_respects_a_per_call_max() -> None:
    # The per-email login limit reuses the same throttle with a higher ceiling, so
    # the override must be honoured independently of the instance default.
    throttle = LoginThrottle(max_failures=10, window_seconds=300)
    for _ in range(12):
        await throttle.record_failure("acct")
    assert await throttle.retry_after("acct") is not None  # over the default 10
    assert await throttle.retry_after("acct", max_failures=20) is None  # under a softer 20
    assert await throttle.retry_after("acct", max_failures=5) is not None  # over a stricter 5


async def test_action_reservations_are_atomic() -> None:
    throttle = LoginThrottle(window_seconds=60)

    results = await asyncio.gather(
        *(throttle.consume("same-action", max_actions=3) for _ in range(20))
    )

    assert sum(result is None for result in results) == 3
    assert all(result is not None for result in results[3:])


def test_local_only_requires_loopback_bind() -> None:
    # A public bind must defeat is_local even when base_url is left at localhost,
    # so production hardening is never silently disabled. The non-local cases need
    # explicit domain keys, since shared fallback material is rejected off-loopback.
    public_keys = {
        "session_secret_key": "session-secret-value-0123456789-abcdef",
        "encryption_key": "encryption-secret-value-0123456789-abcdef",
    }
    assert Settings(base_url="http://localhost:8000", host="127.0.0.1").is_local
    public_bind = Settings(base_url="http://localhost:8000", host="0.0.0.0", **public_keys)
    public_url = Settings(
        base_url="https://monitor.example.com",
        host="127.0.0.1",
        **public_keys,
    )
    assert not public_bind.is_local
    assert not public_url.is_local


def test_insecure_default_secret_is_rejected_off_localhost() -> None:
    with pytest.raises(ValidationError):
        Settings(base_url="https://monitor.example.com", secret_key=INSECURE_SECRET_KEY)
    # Localhost dev is allowed to use the default; public deployments require
    # explicit, separate key domains even if the legacy secret is strong.
    assert Settings(base_url="http://localhost:8000", secret_key=INSECURE_SECRET_KEY).is_local
    with pytest.raises(ValidationError):
        Settings(
            base_url="https://monitor.example.com",
            secret_key="a-real-strong-secret-value-1234567890",
        )
    assert not Settings(
        base_url="https://monitor.example.com",
        session_secret_key="session-secret-value-0123456789-abcdef",
        encryption_key="encryption-secret-value-0123456789-abcdef",
    ).is_local


def test_password_hash_round_trip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_password_hash_is_salted() -> None:
    assert hash_password("same") != hash_password("same")


def test_session_token_round_trip() -> None:
    secret = "a-sufficiently-long-secret-key-value"
    token = issue_session(
        42,
        secret=secret,
        ttl_hours=1,
        token_version=3,
        session_generation=_SESSION_GENERATION,
    )
    claims = read_session(token, secret=secret)
    assert claims.user_id == 42
    assert claims.token_version == 3
    assert claims.session_generation == _SESSION_GENERATION


def test_session_token_rejects_wrong_secret() -> None:
    token = issue_session(
        1,
        secret="secret-one-value-padding-to-32-bytes!",
        ttl_hours=1,
        session_generation=_SESSION_GENERATION,
    )
    with pytest.raises(SessionError):
        read_session(token, secret="secret-two-value-padding-to-32-bytes!")


def test_session_token_accepts_a_configured_previous_key() -> None:
    old = "old-session-key-padding-to-thirty-two-bytes"
    current = "new-session-key-padding-to-thirty-two-bytes"
    token = issue_session(7, secret=old, ttl_hours=1, session_generation=_SESSION_GENERATION)

    assert read_session(token, secret=(current, old)).user_id == 7
    with pytest.raises(SessionError):
        read_session(token, secret=current)


def test_session_token_rejects_expired() -> None:
    secret = "secret-value-padding-to-32-bytes-long!"
    token = issue_session(1, secret=secret, ttl_hours=0, session_generation=_SESSION_GENERATION)
    time.sleep(1)
    with pytest.raises(SessionError):
        read_session(token, secret=secret)


def test_session_token_rejects_legacy_claims_without_generation() -> None:
    secret = "legacy-session-key-padding-to-thirty-two-bytes"
    now = int(time.time())
    token = jwt.encode(
        {"sub": "1", "ver": 0, "iat": now, "exp": now + 3600},
        secret,
        algorithm="HS256",
    )
    with pytest.raises(SessionError):
        read_session(token, secret=secret)


def test_secret_box_round_trip() -> None:
    box = SecretBox("application-secret-key")
    ciphertext = box.encrypt("sk-live-12345")
    assert ciphertext != "sk-live-12345"
    assert box.decrypt(ciphertext) == "sk-live-12345"


def test_secret_box_rejects_foreign_ciphertext() -> None:
    ciphertext = SecretBox("one-key").encrypt("secret")
    assert SecretBox("another-key").decrypt(ciphertext) is None


def test_secret_box_rotates_fallback_ciphertext_to_primary_key() -> None:
    old = SecretBox("old-encryption-key")
    ciphertext = old.encrypt("secret")
    rotating = SecretBox("new-encryption-key", "old-encryption-key")

    rotated = rotating.rotate(ciphertext)

    assert rotated is not None and rotated != ciphertext
    assert rotating.decrypt(rotated) == "secret"
    assert old.decrypt(rotated) is None


def test_secret_box_reads_and_versions_legacy_fernet_ciphertext() -> None:
    key = "legacy-application-key"
    digest = hashlib.sha256(key.encode()).digest()
    legacy = Fernet(base64.urlsafe_b64encode(digest)).encrypt(b"secret").decode()
    box = SecretBox(key)

    assert box.decrypt(legacy) == "secret"
    rotated = box.rotate(legacy)
    assert rotated is not None and rotated.startswith("dw1:")
