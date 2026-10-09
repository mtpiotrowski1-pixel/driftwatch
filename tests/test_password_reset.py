"""Password reset: token consumption, single-use, session revocation, and the
no-enumeration request endpoint."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from sqlalchemy import select

from driftwatch.api import auth
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.enums import AccountEmailStatus
from driftwatch.models import AccountEmailJob, AuditEvent, User
from driftwatch.notifications.render import render_password_reset_email
from driftwatch.security.tokens import (
    PURPOSE_PASSWORD_RESET,
    issue_scoped_token,
    issue_session,
)


async def _register(client: httpx.AsyncClient, email: str, password: str) -> int:
    response = await client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _session_generation(database: Database, user_id: int) -> str:
    async with database.session() as session:
        user = await session.get(User, user_id)
        assert user is not None
        return user.session_generation


def _reset_token(
    settings: Settings,
    user_id: int,
    session_generation: str,
    *,
    version: int = 0,
) -> str:
    return issue_scoped_token(
        user_id,
        secret=settings.secret_key,
        purpose=PURPOSE_PASSWORD_RESET,
        ttl_seconds=1800,
        token_version=version,
        session_generation=session_generation,
    )


async def test_reset_with_valid_token_changes_password(
    client: httpx.AsyncClient, settings: Settings, database: Database
) -> None:
    user_id = await _register(client, "reset@example.com", "password123")
    client.cookies.clear()

    response = await client.post(
        "/api/auth/reset-password",
        json={
            "token": _reset_token(settings, user_id, await _session_generation(database, user_id)),
            "new_password": "brand-new-pass",
        },
    )
    assert response.status_code == 204

    async with database.session() as session:
        event = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "account.password_reset",
                    AuditEvent.target_id == str(user_id),
                )
            )
        ).scalar_one()
        assert event.target_label == "reset@example.com"
        assert event.details == {}

    old = await client.post(
        "/api/auth/login", json={"email": "reset@example.com", "password": "password123"}
    )
    new = await client.post(
        "/api/auth/login", json={"email": "reset@example.com", "password": "brand-new-pass"}
    )
    assert old.status_code == 401
    assert new.status_code == 200


async def test_reset_token_is_single_use(
    client: httpx.AsyncClient, settings: Settings, database: Database
) -> None:
    user_id = await _register(client, "once@example.com", "password123")
    client.cookies.clear()
    token = _reset_token(settings, user_id, await _session_generation(database, user_id))

    first = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "first-new-pass"}
    )
    second = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "second-new-pass"}
    )
    assert first.status_code == 204
    assert second.status_code == 400  # token_version bumped → the link cannot be replayed


async def test_concurrent_reset_consumes_token_once_on_sqlite(
    client: httpx.AsyncClient,
    settings: Settings,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _register(client, "parallel-reset@example.com", "password123")
    token = _reset_token(settings, user_id, await _session_generation(database, user_id))
    entered = 0
    both_loaded = asyncio.Event()
    real_hash = auth.ahash_password

    async def hash_after_both_reads(password: str) -> str:
        nonlocal entered
        entered += 1
        if entered == 2:
            both_loaded.set()
        await asyncio.wait_for(both_loaded.wait(), timeout=5)
        return await real_hash(password)

    monkeypatch.setattr(auth, "ahash_password", hash_after_both_reads)
    responses = await asyncio.gather(
        *(
            client.post("/api/auth/reset-password", json={"token": token, "new_password": password})
            for password in ("first-parallel-password", "second-parallel-password")
        )
    )
    assert sorted(response.status_code for response in responses) == [204, 400]
    async with database.session() as session:
        user = await session.get(User, user_id)
        assert user is not None and user.token_version == 1
        events = (
            await session.scalars(
                select(AuditEvent).where(AuditEvent.action == "account.password_reset")
            )
        ).all()
        assert len(events) == 1


async def test_reset_revokes_existing_sessions(
    client: httpx.AsyncClient, settings: Settings, database: Database
) -> None:
    user_id = await _register(client, "live@example.com", "password123")
    assert (await client.get("/api/auth/me")).status_code == 200  # registration logged us in

    reset = await client.post(
        "/api/auth/reset-password",
        json={
            "token": _reset_token(settings, user_id, await _session_generation(database, user_id)),
            "new_password": "rotated-pass",
        },
    )
    assert reset.status_code == 204
    # The pre-reset session cookie is now stale (token_version bumped).
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_reset_rejects_a_session_token(
    client: httpx.AsyncClient, settings: Settings, database: Database
) -> None:
    user_id = await _register(client, "confuse@example.com", "password123")
    client.cookies.clear()
    session_token = issue_session(
        user_id,
        secret=settings.secret_key,
        ttl_hours=1,
        session_generation=await _session_generation(database, user_id),
    )
    response = await client.post(
        "/api/auth/reset-password", json={"token": session_token, "new_password": "whatever-pass"}
    )
    assert response.status_code == 400  # purpose mismatch — a session token is not a reset token


async def test_reset_rejects_garbage_token(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/reset-password", json={"token": "not-a-real-token", "new_password": "whatever1"}
    )
    assert response.status_code == 400


async def test_request_reset_does_not_reveal_account_existence(
    client: httpx.AsyncClient,
    database: Database,
) -> None:
    await _register(client, "real@example.com", "password123")
    client.cookies.clear()
    known = await client.post(
        "/api/auth/request-password-reset", json={"email": "real@example.com"}
    )
    known_retry = await client.post(
        "/api/auth/request-password-reset", json={"email": "real@example.com"}
    )
    unknown = await client.post(
        "/api/auth/request-password-reset", json={"email": "ghost@example.com"}
    )
    assert known.status_code == 204
    assert known_retry.status_code == 204
    assert unknown.status_code == 204
    assert known.content == known_retry.content == unknown.content

    async with database.session() as session:
        jobs = list(
            (await session.execute(select(AccountEmailJob).order_by(AccountEmailJob.id))).scalars()
        )
    assert len(jobs) == 2
    assert [job.status for job in jobs] == [
        AccountEmailStatus.PENDING,
        AccountEmailStatus.PENDING,
    ]
    assert [job.attempt_count for job in jobs] == [0, 0]
    assert sum(job.user_id is None for job in jobs) == 1


def test_reset_email_carries_the_configured_brand() -> None:
    # A white-label deployment must not sign its reset mail "Driftwatch".
    message = render_password_reset_email(
        reset_url="https://app.example/reset-password#token=t",
        valid_minutes=30,
        brand_name="Acme Watch",
    )
    assert message.subject == "Reset your Acme Watch password"
    assert "Acme Watch" in message.text_body
    assert "Driftwatch" not in message.html_body


async def test_request_reset_is_rate_limited(client: httpx.AsyncClient) -> None:
    await _register(client, "flood@example.com", "password123")
    client.cookies.clear()
    statuses = [
        (
            await client.post(
                "/api/auth/request-password-reset", json={"email": "flood@example.com"}
            )
        ).status_code
        for _ in range(12)
    ]
    assert 429 in statuses  # the per-address / per-client limit eventually trips
