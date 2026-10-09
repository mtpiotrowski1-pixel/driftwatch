"""Abuse guards for administrator-triggered outbound integration tests."""

from __future__ import annotations

import httpx

from driftwatch.db import Database
from tests.conftest import set_test_user_password


async def _create_org_admin(
    client: httpx.AsyncClient,
    database: Database,
    *,
    email: str = "tenant-admin@example.com",
    password: str = "password123",
) -> None:
    step_up = await client.post("/api/auth/step-up", json={"password": "supersecret123"})
    assert step_up.status_code == 204, step_up.text
    org = (await client.post("/api/organizations", json={"name": "Guarded tenant"})).json()
    headers = {"X-Acting-Org": str(org["id"])}
    tenant_step_up = await client.post(
        "/api/auth/step-up",
        json={"password": "supersecret123"},
        headers=headers,
    )
    assert tenant_step_up.status_code == 204, tenant_step_up.text
    created = await client.post(
        "/api/users",
        json={"email": email, "is_admin": True},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    await set_test_user_password(database, email, password)
    logged_in = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert logged_in.status_code == 200, logged_in.text


async def test_org_admin_test_email_is_limited_to_own_address(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    await _create_org_admin(admin_client, database)

    arbitrary = await admin_client.post(
        "/api/settings/test-email", json={"to": "victim@example.com"}
    )
    assert arbitrary.status_code == 403, arbitrary.text

    own = await admin_client.post(
        "/api/settings/test-email", json={"to": "tenant-admin@example.com"}
    )
    assert own.status_code == 200, own.text
    assert own.json()["channel"] == "log"


async def test_org_admin_cannot_exercise_inherited_platform_webhook(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    step_up = await admin_client.post("/api/auth/step-up", json={"password": "supersecret123"})
    assert step_up.status_code == 204, step_up.text
    configured = await admin_client.put(
        "/api/settings",
        json={"notification_webhook_url": "https://example.com/platform-hook"},
    )
    assert configured.status_code == 200, configured.text
    await _create_org_admin(admin_client, database)

    response = await admin_client.post("/api/settings/test-webhook")
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == (
        "Configure an organization-owned webhook before sending a test"
    )


async def test_integration_tests_have_a_per_actor_rate_limit(
    admin_client: httpx.AsyncClient,
) -> None:
    for index in range(3):
        response = await admin_client.post(
            "/api/settings/test-email", json={"to": f"ops-{index}@example.com"}
        )
        assert response.status_code == 200, response.text

    limited = await admin_client.post(
        "/api/settings/test-email", json={"to": "ops-final@example.com"}
    )
    assert limited.status_code == 429, limited.text
    assert int(limited.headers["Retry-After"]) >= 1
