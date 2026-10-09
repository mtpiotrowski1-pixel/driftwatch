"""A copied second-factor challenge cannot complete more than one login."""

from __future__ import annotations

import time

import httpx
import pytest
from sqlalchemy import select

from driftwatch.api import auth
from driftwatch.api.deps import PENDING_TOTP_COOKIE
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.models import User
from driftwatch.security import two_factor
from driftwatch.security.tokens import PURPOSE_PASSWORD_RESET, issue_scoped_token


async def test_unknown_and_known_email_both_verify_password(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await client.post(
        "/api/auth/register", json={"email": "user@example.com", "password": "password123"}
    )
    calls: list[str] = []
    original = auth.averify_password

    async def record(password: str, encoded: str) -> bool:
        calls.append(encoded)
        return await original(password, encoded)

    monkeypatch.setattr(auth, "averify_password", record)
    for email in ("missing@example.com", "user@example.com"):
        response = await client.post("/api/auth/login", json={"email": email, "password": "wrong"})
        assert response.status_code == 401
    assert len(calls) == 2
    assert calls[0] == auth._DUMMY_PASSWORD_HASH
    assert calls[1] != calls[0]


async def test_challenge_and_totp_step_are_single_use(client: httpx.AsyncClient) -> None:
    credentials = {"email": "user@example.com", "password": "password123"}
    assert (await client.post("/api/auth/register", json=credentials)).status_code == 201
    assert (
        await client.post("/api/auth/step-up", json={"password": "password123"})
    ).status_code == 204
    setup = await client.post("/api/auth/totp/setup")
    secret = setup.json()["secret"]
    instant = time.time()
    code = two_factor.generate_code(secret, at=instant)
    assert (await client.post("/api/auth/totp/enable", json={"code": code})).status_code == 200
    await client.post("/api/auth/logout")
    assert (await client.post("/api/auth/login", json=credentials)).status_code == 200
    copied = client.cookies.get(PENDING_TOTP_COOKIE)
    assert copied is not None
    assert (await client.post("/api/auth/login/totp", json={"code": code})).status_code == 200
    client.cookies.clear()
    client.cookies.set(PENDING_TOTP_COOKIE, copied)
    assert (await client.post("/api/auth/login/totp", json={"code": code})).status_code == 401
    # A fresh password step still cannot reuse the accepted TOTP counter.
    assert (await client.post("/api/auth/login", json=credentials)).status_code == 200
    assert (await client.post("/api/auth/login/totp", json={"code": code})).status_code == 401
    next_code = two_factor.generate_code(secret, at=instant + 30)
    assert (await client.post("/api/auth/login/totp", json={"code": next_code})).status_code == 200


async def test_account_budget_precedes_verify_and_recovery_restores_access(
    client: httpx.AsyncClient,
    database: Database,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = {"email": "user@example.com", "password": "password123"}
    assert (await client.post("/api/auth/register", json=credentials)).status_code == 201
    calls = 0

    async def verify(password: str, encoded: str) -> bool:
        nonlocal calls
        calls += 1
        return password == "recovered-password-123"

    monkeypatch.setattr(auth, "averify_password", verify)
    transport = client._transport
    assert isinstance(transport, httpx.ASGITransport)
    for number in range(auth._LOGIN_EMAIL_MAX + 1):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=transport.app, client=(f"198.51.100.{number + 1}", 1)
            ),
            base_url=settings.base_url,
        ) as source:
            response = await source.post(
                "/api/auth/login", json={"email": credentials["email"], "password": "wrong"}
            )
            assert response.status_code == (401 if number < auth._LOGIN_EMAIL_MAX else 429)
    assert calls == auth._LOGIN_EMAIL_MAX
    assert response.headers["Retry-After"]
    # Possession of a valid reset token is a separate recovery proof. Merely
    # requesting a reset or knowing the correct password does not clear a budget.
    async with database.session() as session:
        user = await session.scalar(select(User).where(User.email == credentials["email"]))
        assert user is not None
        token = issue_scoped_token(
            user.id,
            secret=settings.token_secret,
            purpose=PURPOSE_PASSWORD_RESET,
            ttl_seconds=300,
            token_version=user.token_version,
            session_generation=user.session_generation,
        )
    reset = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "recovered-password-123"}
    )
    assert reset.status_code == 204, reset.text
    recovered = await client.post(
        "/api/auth/login",
        json={"email": credentials["email"], "password": "recovered-password-123"},
    )
    assert recovered.status_code == 200, recovered.text
    assert calls == auth._LOGIN_EMAIL_MAX + 1
