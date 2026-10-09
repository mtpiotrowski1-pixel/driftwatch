"""Tests for the settings test-email endpoint."""

from __future__ import annotations

import httpx


async def test_test_email_uses_configured_channel(admin_client: httpx.AsyncClient) -> None:
    # With no SMTP/Brevo credentials configured, delivery falls back to the log
    # channel, which always "delivers" — enough to confirm the wiring.
    response = await admin_client.post("/api/settings/test-email", json={"to": "ops@example.com"})
    assert response.status_code == 200
    body = response.json()
    assert body["delivered"] is True
    assert body["channel"] == "log"


async def test_test_email_requires_admin(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "admin@example.com", "password": "password123"}
    )
    await client.post(
        "/api/auth/register", json={"email": "member@example.com", "password": "password123"}
    )  # session is now the member
    response = await client.post("/api/settings/test-email", json={"to": "ops@example.com"})
    assert response.status_code == 403
