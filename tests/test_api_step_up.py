"""Step-up re-authentication guards the most destructive operator actions."""

from __future__ import annotations

import httpx
from tests.conftest import set_test_user_password

from driftwatch.api.deps import STEP_UP_COOKIE
from driftwatch.db import Database

_ADMIN_PASSWORD = "supersecret123"


async def _step_up(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/auth/step-up", json={"password": _ADMIN_PASSWORD})
    assert response.status_code == 204, response.text


async def _create_org(client: httpx.AsyncClient, name: str) -> int:
    await _step_up(client)
    response = await client.post("/api/organizations", json={"name": name})
    assert response.status_code == 201, response.text
    client.cookies.delete(STEP_UP_COOKIE)
    return int(response.json()["id"])


async def test_destructive_actions_require_step_up(admin_client: httpx.AsyncClient) -> None:
    org_id = await _create_org(admin_client, "Doomed")

    # Without a fresh re-authentication, both guarded actions answer 428.
    assert (await admin_client.delete(f"/api/organizations/{org_id}")).status_code == 428
    assert (await admin_client.get("/api/admin/backup")).status_code == 428

    # The wrong password does not unlock anything.
    assert (
        await admin_client.post("/api/auth/step-up", json={"password": "wrong"})
    ).status_code == 400

    stepped = await admin_client.post("/api/auth/step-up", json={"password": _ADMIN_PASSWORD})
    assert stepped.status_code == 204

    # With a valid step-up cookie the guarded routes are no longer blocked on
    # re-auth. Permanent tenant deletion is still rejected by the lifecycle
    # policy, while backup proceeds to its own backend checks.
    assert (await admin_client.delete(f"/api/organizations/{org_id}")).status_code == 409
    assert (await admin_client.get("/api/admin/backup")).status_code != 428


async def test_step_up_does_not_survive_a_password_change(admin_client: httpx.AsyncClient) -> None:
    org_id = await _create_org(admin_client, "Doomed")
    assert (
        await admin_client.post("/api/auth/step-up", json={"password": _ADMIN_PASSWORD})
    ).status_code == 204

    # Changing the password bumps the token version, invalidating the step-up too.
    changed = await admin_client.post(
        "/api/auth/change-password",
        json={"current_password": _ADMIN_PASSWORD, "new_password": "newsupersecret123"},
    )
    assert changed.status_code == 204
    assert (await admin_client.delete(f"/api/organizations/{org_id}")).status_code == 428


async def test_step_up_requires_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/auth/step-up", json={"password": "x"})).status_code == 401


async def test_operator_step_up_is_bound_to_the_confirmed_tenant_or_instance(
    admin_client: httpx.AsyncClient,
) -> None:
    organization_a = await _create_org(admin_client, "Step-up tenant A")
    organization_b = await _create_org(admin_client, "Step-up tenant B")
    headers_a = {"X-Acting-Org": str(organization_a)}
    headers_b = {"X-Acting-Org": str(organization_b)}

    tenant_step_up = await admin_client.post(
        "/api/auth/step-up",
        headers=headers_a,
        json={"password": _ADMIN_PASSWORD},
    )
    assert tenant_step_up.status_code == 204, tenant_step_up.text
    same_tenant = await admin_client.put(
        "/api/settings",
        headers=headers_a,
        json={"notification_webhook_url": "https://tenant-a.example.com/hook"},
    )
    assert same_tenant.status_code == 200, same_tenant.text

    wrong_tenant = await admin_client.put(
        "/api/settings",
        headers=headers_b,
        json={"notification_webhook_url": "https://tenant-b.example.com/hook"},
    )
    assert wrong_tenant.status_code == 428, wrong_tenant.text
    wrong_instance = await admin_client.post(
        "/api/organizations",
        json={"name": "Tenant proof must not unlock the instance"},
    )
    assert wrong_instance.status_code == 428, wrong_instance.text

    instance_step_up = await admin_client.post(
        "/api/auth/step-up",
        json={"password": _ADMIN_PASSWORD},
    )
    assert instance_step_up.status_code == 204, instance_step_up.text
    same_instance = await admin_client.post(
        "/api/organizations",
        json={"name": "Instance-scoped proof"},
    )
    assert same_instance.status_code == 201, same_instance.text
    wrong_tenant_from_instance = await admin_client.put(
        "/api/settings",
        headers=headers_b,
        json={"notification_webhook_url": "https://tenant-b.example.com/hook"},
    )
    assert wrong_tenant_from_instance.status_code == 428, wrong_tenant_from_instance.text


async def test_org_admin_step_up_ignores_an_acting_org_header(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    organization = await _create_org(admin_client, "Bound org admin")
    other_organization = await _create_org(admin_client, "Unrelated tenant")
    own_headers = {"X-Acting-Org": str(organization)}

    stepped_operator = await admin_client.post(
        "/api/auth/step-up",
        headers=own_headers,
        json={"password": _ADMIN_PASSWORD},
    )
    assert stepped_operator.status_code == 204, stepped_operator.text
    created = await admin_client.post(
        "/api/users",
        headers=own_headers,
        json={"email": "bound-admin@example.com", "is_admin": True},
    )
    assert created.status_code == 201, created.text
    await set_test_user_password(database, "bound-admin@example.com")

    logged_in = await admin_client.post(
        "/api/auth/login",
        json={"email": "bound-admin@example.com", "password": "password123"},
    )
    assert logged_in.status_code == 200, logged_in.text
    misleading_headers = {"X-Acting-Org": str(other_organization)}
    stepped_admin = await admin_client.post(
        "/api/auth/step-up",
        headers=misleading_headers,
        json={"password": "password123"},
    )
    assert stepped_admin.status_code == 204, stepped_admin.text
    saved = await admin_client.put(
        "/api/settings",
        headers=misleading_headers,
        json={"notification_webhook_url": "https://bound-admin.example.com/hook"},
    )
    assert saved.status_code == 200, saved.text


async def test_tenant_and_entitlement_mutations_require_step_up(
    admin_client: httpx.AsyncClient,
) -> None:
    plan_body = {"key": "guarded", "name": "Guarded"}
    assert (
        await admin_client.post("/api/organizations", json={"name": "Guarded tenant"})
    ).status_code == 428
    assert (await admin_client.post("/api/plans", json=plan_body)).status_code == 428

    await _step_up(admin_client)
    organization = (
        await admin_client.post("/api/organizations", json={"name": "Guarded tenant"})
    ).json()
    plan = (await admin_client.post("/api/plans", json=plan_body)).json()
    admin_client.cookies.delete(STEP_UP_COOKIE)

    # A label-only edit does not alter access, billing, or resource limits.
    renamed = await admin_client.patch(
        f"/api/organizations/{organization['id']}", json={"name": "Renamed tenant"}
    )
    assert renamed.status_code == 200, renamed.text

    assert (
        await admin_client.patch(
            f"/api/organizations/{organization['id']}", json={"is_active": False}
        )
    ).status_code == 428
    assert (
        await admin_client.patch(f"/api/plans/{plan['id']}", json={"max_sites": 10})
    ).status_code == 428
    assert (await admin_client.delete(f"/api/plans/{plan['id']}")).status_code == 428
    assert (await admin_client.put("/api/plans/pricing", json={"base_fee": 25})).status_code == 428

    await _step_up(admin_client)
    assert (
        await admin_client.patch(
            f"/api/organizations/{organization['id']}", json={"is_active": False}
        )
    ).status_code == 200
    assert (
        await admin_client.patch(f"/api/plans/{plan['id']}", json={"max_sites": 10})
    ).status_code == 200
    assert (await admin_client.put("/api/plans/pricing", json={"base_fee": 25})).status_code == 200
    assert (await admin_client.delete(f"/api/plans/{plan['id']}")).status_code == 204


async def test_secret_settings_require_step_up(admin_client: httpx.AsyncClient) -> None:
    blocked = await admin_client.put(
        "/api/settings",
        json={"notification_webhook_url": "https://hooks.example.com/driftwatch"},
    )
    assert blocked.status_code == 428

    stepped = await admin_client.post(
        "/api/auth/step-up",
        json={"password": _ADMIN_PASSWORD},
    )
    assert stepped.status_code == 204
    saved = await admin_client.put(
        "/api/settings",
        json={"notification_webhook_url": "https://hooks.example.com/driftwatch"},
    )
    assert saved.status_code == 200
    assert saved.json()["notification_webhook_url"] == "********"

    admin_client.cookies.delete(STEP_UP_COOKIE)
    blocked_clear = await admin_client.put(
        "/api/settings",
        json={"clear_secret_keys": ["notification_webhook_url"]},
    )
    assert blocked_clear.status_code == 428

    await _step_up(admin_client)
    cleared = await admin_client.put(
        "/api/settings",
        json={"clear_secret_keys": ["notification_webhook_url"]},
    )
    assert cleared.status_code == 200
    assert "notification_webhook_url" not in cleared.json()


async def test_delivery_route_settings_require_step_up(
    admin_client: httpx.AsyncClient,
) -> None:
    for payload in (
        {"email_provider": "smtp"},
        {"smtp_host": "smtp.example.com"},
        {"smtp_port": 465},
        {"smtp_username": "mailer"},
        {"smtp_security": "ssl"},
        {"notification_from_email": "alerts@example.com"},
    ):
        response = await admin_client.put("/api/settings", json=payload)
        assert response.status_code == 428, (payload, response.text)

    await _step_up(admin_client)
    saved = await admin_client.put(
        "/api/settings",
        json={"email_provider": "smtp", "smtp_host": "smtp.example.com"},
    )
    assert saved.status_code == 200, saved.text


async def test_step_up_is_throttled_per_account_and_client(
    admin_client: httpx.AsyncClient,
) -> None:
    statuses = [
        (
            await admin_client.post(
                "/api/auth/step-up",
                json={"password": "wrong"},
            )
        ).status_code
        for _ in range(11)
    ]
    assert statuses[:10] == [400] * 10
    assert statuses[10] == 429
    blocked = await admin_client.post(
        "/api/auth/step-up",
        json={"password": _ADMIN_PASSWORD},
    )
    assert blocked.status_code == 429
