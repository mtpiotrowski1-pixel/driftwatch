"""The settings API is scoped to the caller: the operator edits instance
defaults; an org-admin reads the effective view and writes only their org."""

from __future__ import annotations

import httpx

from driftwatch.db import Database
from tests.conftest import set_test_user_password

_SUPERADMIN = ("admin@example.com", "supersecret123")


async def _login(client: httpx.AsyncClient, email: str, password: str) -> None:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


async def _make_org_admin(
    admin_client: httpx.AsyncClient,
    database: Database,
    org_name: str,
    email: str,
    password: str = "password123",
) -> int:
    step_up = await admin_client.post("/api/auth/step-up", json={"password": "supersecret123"})
    assert step_up.status_code == 204, step_up.text
    org = (await admin_client.post("/api/organizations", json={"name": org_name})).json()
    # The operator "enters" the org (X-Acting-Org) so the new admin lands in it.
    headers = {"X-Acting-Org": str(org["id"])}
    tenant_step_up = await admin_client.post(
        "/api/auth/step-up",
        json={"password": "supersecret123"},
        headers=headers,
    )
    assert tenant_step_up.status_code == 204, tenant_step_up.text
    created = await admin_client.post(
        "/api/users",
        json={"email": email, "is_admin": True},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    await set_test_user_password(database, email, password)
    return int(org["id"])


async def test_org_admin_inherits_then_overrides(
    admin_client: httpx.AsyncClient, database: Database
) -> None:
    assert (
        await admin_client.put("/api/settings", json={"base_prompt": "instance default"})
    ).status_code == 200
    await _make_org_admin(admin_client, database, "Acme", "acme-admin@example.com")

    await _login(admin_client, "acme-admin@example.com", "password123")
    # The org has no override yet, so the effective value is the inherited default,
    # and /defaults exposes what a blank field would use.
    assert (await admin_client.get("/api/settings")).json().get("base_prompt") == "instance default"
    assert (await admin_client.get("/api/settings/defaults")).json().get(
        "base_prompt"
    ) == "instance default"

    saved = await admin_client.put("/api/settings", json={"base_prompt": "acme rules"})
    assert saved.json()["base_prompt"] == "acme rules"
    # The override wins for the org, but /defaults still shows the inherited value.
    assert (await admin_client.get("/api/settings")).json()["base_prompt"] == "acme rules"
    assert (await admin_client.get("/api/settings/defaults")).json()["base_prompt"] == (
        "instance default"
    )

    # The operator's instance default is untouched by the org's override.
    await _login(admin_client, *_SUPERADMIN)
    assert (await admin_client.get("/api/settings")).json()["base_prompt"] == "instance default"


async def test_org_settings_do_not_leak_between_orgs(
    admin_client: httpx.AsyncClient, database: Database
) -> None:
    await admin_client.put("/api/settings", json={"base_prompt": "instance default"})
    await _make_org_admin(admin_client, database, "Org A", "org-a-admin@example.com")
    await _make_org_admin(admin_client, database, "Org B", "org-b-admin@example.com")

    await _login(admin_client, "org-a-admin@example.com", "password123")
    await admin_client.put("/api/settings", json={"base_prompt": "A only"})

    await _login(admin_client, "org-b-admin@example.com", "password123")
    # B never sees A's override — it inherits the instance default.
    assert (await admin_client.get("/api/settings")).json()["base_prompt"] == "instance default"


async def test_factory_defaults_are_exposed_to_admins(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/api/settings/factory-defaults")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["base_prompt"].strip()
    assert data["importance_rules"].strip()
    assert "script" in data["stripped_tags"]
    # Value-wide heuristics were removed because they erased visible IDs/dates.
    # Factory metadata must not advertise patterns the cleaner no longer uses.
    assert data["volatile_patterns"] == []
    assert set(data["response_fields"]) == {"significant", "headline", "summary"}


async def test_factory_defaults_require_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/settings/factory-defaults")).status_code == 401


async def test_database_app_base_url_override_is_retired(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    rejected_for_operator = await admin_client.put(
        "/api/settings", json={"app_base_url": "https://instance.example"}
    )
    assert rejected_for_operator.status_code == 422
    await _make_org_admin(admin_client, database, "Acme", "acme-admin@example.com")

    await _login(admin_client, "acme-admin@example.com", "password123")
    rejected = await admin_client.put(
        "/api/settings", json={"app_base_url": "https://hijack.example"}
    )
    assert rejected.status_code == 422, rejected.text
    # The retired value is neither writable nor exposed. Deployment BASE_URL is
    # the only source for account and notification links.
    assert "app_base_url" not in (await admin_client.get("/api/settings")).json()


async def test_org_admin_cannot_override_platform_credentials_or_ai_costs(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    await _make_org_admin(admin_client, database, "Acme", "acme-admin@example.com")
    await _login(admin_client, "acme-admin@example.com", "password123")

    for key, value in (
        ("openai_api_key", "sk-tenant"),
        ("openai_model", "tenant-model"),
        ("openai_price_input_per_1m", 0),
        ("smtp_host", "smtp.tenant.example"),
        ("brevo_api_key", "tenant-key"),
        ("notification_from_email", "spoof@example.com"),
    ):
        response = await admin_client.put("/api/settings", json={key: value})
        assert response.status_code == 400, (key, response.text)
        assert key in response.json()["detail"]


async def test_technical_alert_recipients_must_be_unique_positive_and_tenant_owned(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    await _make_org_admin(admin_client, database, "Org A", "org-a-admin@example.com")
    await _make_org_admin(admin_client, database, "Org B", "org-b-admin@example.com")

    await _login(admin_client, "org-b-admin@example.com", "password123")
    foreign_id = int(
        (
            await admin_client.post("/api/recipients", json={"email": "foreign-alerts@example.com"})
        ).json()["id"]
    )

    await _login(admin_client, "org-a-admin@example.com", "password123")
    own_id = int(
        (
            await admin_client.post("/api/recipients", json={"email": "own-alerts@example.com"})
        ).json()["id"]
    )
    saved = await admin_client.put(
        "/api/settings", json={"technical_alert_recipient_ids": [own_id]}
    )
    assert saved.status_code == 200, saved.text

    for invalid_ids in ([foreign_id], [own_id, own_id], [0], [-1], list(range(1, 52))):
        rejected = await admin_client.put(
            "/api/settings", json={"technical_alert_recipient_ids": invalid_ids}
        )
        assert rejected.status_code == 400, (invalid_ids, rejected.text)

    # A failed replacement must leave the previously validated selection intact.
    stored = (await admin_client.get("/api/settings")).json()
    assert stored["technical_alert_recipient_ids"] == f"[{own_id}]"


async def test_instance_settings_cannot_reference_tenant_recipient_ids(
    admin_client: httpx.AsyncClient,
) -> None:
    recipient = await admin_client.post(
        "/api/recipients", json={"email": "instance-alerts@example.com"}
    )
    assert recipient.status_code == 201, recipient.text

    rejected = await admin_client.put(
        "/api/settings",
        json={"technical_alert_recipient_ids": [recipient.json()["id"]]},
    )
    assert rejected.status_code == 400, rejected.text
    assert "organization" in rejected.json()["detail"].lower()
