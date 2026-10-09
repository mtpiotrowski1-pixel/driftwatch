"""Tests for the authentication endpoints and access control."""

from __future__ import annotations

import httpx

from driftwatch.api.deps import (
    PENDING_TOTP_COOKIE,
    SESSION_COOKIE,
    STEP_UP_COOKIE,
    SUPPORT_ACCESS_COOKIE,
)


async def test_health_is_public(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "routing_ready": True,
        "dependencies": {
            "database": "ready",
            "scheduler": "disabled",
            "capture": "not_probed",
        },
    }

    liveness = await client.get("/livez")
    assert liveness.status_code == 200
    assert liveness.json() == {"status": "ok"}


async def test_protected_route_requires_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/sites")).status_code == 401


async def test_first_registration_becomes_admin(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": "first@example.com", "password": "password123"},
    )
    assert response.status_code == 201
    assert response.json()["is_admin"] is True


async def test_second_registration_is_member(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "first@example.com", "password": "password123"}
    )
    response = await client.post(
        "/api/auth/register", json={"email": "second@example.com", "password": "password123"}
    )
    assert response.status_code == 201
    assert response.json()["is_admin"] is False


async def test_duplicate_registration_conflicts(client: httpx.AsyncClient) -> None:
    payload = {"email": "dup@example.com", "password": "password123"}
    await client.post("/api/auth/register", json=payload)
    assert (await client.post("/api/auth/register", json=payload)).status_code == 409


async def test_login_logout_cycle(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "user@example.com", "password": "password123"}
    )
    await client.post("/api/auth/logout")
    assert (await client.get("/api/auth/me")).status_code == 401

    bad = await client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "wrong"}
    )
    assert bad.status_code == 401

    good = await client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "password123"}
    )
    assert good.status_code == 200
    assert (await client.get("/api/auth/me")).json()["email"] == "user@example.com"


async def test_logout_clears_every_authentication_cookie(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/auth/logout")
    set_cookies = response.headers.get_list("set-cookie")

    for name in (
        SESSION_COOKIE,
        PENDING_TOTP_COOKIE,
        STEP_UP_COOKIE,
        SUPPORT_ACCESS_COOKIE,
    ):
        matching = [header for header in set_cookies if header.startswith(f"{name}=")]
        assert matching, f"logout did not clear {name}"
        assert "Max-Age=0" in matching[0]


async def test_short_password_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register", json={"email": "x@example.com", "password": "short"}
    )
    assert response.status_code == 422


async def test_change_password(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "user@example.com", "password": "password123"}
    )
    wrong = await client.post(
        "/api/auth/change-password",
        json={"current_password": "nope", "new_password": "newpassword123"},
    )
    assert wrong.status_code == 400

    changed = await client.post(
        "/api/auth/change-password",
        json={"current_password": "password123", "new_password": "newpassword123"},
    )
    assert changed.status_code == 204

    await client.post("/api/auth/logout")
    relogin = await client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "newpassword123"}
    )
    assert relogin.status_code == 200


async def test_change_password_revokes_existing_sessions(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "user@example.com", "password": "password123"}
    )
    old_cookie = client.cookies.get(SESSION_COOKIE)
    assert old_cookie is not None

    changed = await client.post(
        "/api/auth/change-password",
        json={"current_password": "password123", "new_password": "newpassword123"},
    )
    assert changed.status_code == 204

    # A session token issued before the password change must no longer work.
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, old_cookie)
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_login_is_throttled_after_repeated_failures(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "user@example.com", "password": "password123"}
    )
    bad = {"email": "user@example.com", "password": "wrong"}
    statuses = [(await client.post("/api/auth/login", json=bad)).status_code for _ in range(11)]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429


async def test_change_password_is_throttled(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "user@example.com", "password": "password123"}
    )
    bad = {"current_password": "wrong", "new_password": "newpassword123"}
    statuses = [
        (await client.post("/api/auth/change-password", json=bad)).status_code for _ in range(11)
    ]
    assert statuses[:10] == [400] * 10
    assert statuses[10] == 429
