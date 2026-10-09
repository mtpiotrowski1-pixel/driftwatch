"""Privileged actions leave an immutable, tenant-scoped forensic trail."""

from __future__ import annotations

import httpx
import pytest
from tests.conftest import set_test_user_password

from driftwatch.api.deps import STEP_UP_COOKIE
from driftwatch.db import Database
from driftwatch.models import AuditEvent, User
from driftwatch.security import two_factor


async def _step_up(
    client: httpx.AsyncClient,
    password: str,
    organization_id: int | None = None,
) -> None:
    headers = {"X-Acting-Org": str(organization_id)} if organization_id is not None else None
    response = await client.post(
        "/api/auth/step-up",
        headers=headers,
        json={"password": password},
    )
    assert response.status_code == 204, response.text


async def _create_org_admin(
    client: httpx.AsyncClient,
    database: Database,
    org_id: int,
    email: str,
    password: str = "password123",
) -> None:
    await _step_up(client, "supersecret123", org_id)
    response = await client.post(
        "/api/users",
        json={"email": email, "is_admin": True},
        headers={"X-Acting-Org": str(org_id)},
    )
    assert response.status_code == 201, response.text
    await set_test_user_password(database, email, password)


async def _login(client: httpx.AsyncClient, email: str, password: str) -> None:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


async def test_privileged_mutations_are_recorded_without_secret_values(
    admin_client: httpx.AsyncClient,
) -> None:
    await _step_up(admin_client, "supersecret123")
    org = (await admin_client.post("/api/organizations", json={"name": "Acme"})).json()
    settings_response = await admin_client.put(
        "/api/settings",
        json={
            "openai_api_key": "sk-never-store-in-audit",
            "openai_model": "gpt-test",
            # A synthetic model needs explicit prices before plan estimation.
            "openai_price_input_per_1m": 1.0,
            "openai_price_output_per_1m": 2.0,
        },
    )
    assert settings_response.status_code == 200, settings_response.text
    plan_response = await admin_client.post(
        "/api/plans",
        json={
            "key": "starter",
            "name": "Starter",
            "max_sites": 3,
            "monthly_ai_check_limit": 10,
            "currency": "USD",
        },
    )
    assert plan_response.status_code == 201, plan_response.text

    response = await admin_client.get("/api/audit-events", params={"limit": 200})
    assert response.status_code == 200, response.text
    events = response.json()
    actions = {event["action"] for event in events}
    assert {"settings.updated", "plan.created"} <= actions
    assert "organization.created" not in actions
    tenant_events = (
        await admin_client.get(
            "/api/audit-events",
            headers={"X-Acting-Org": str(org["id"])},
            params={"limit": 200},
        )
    ).json()
    assert any(
        event["action"] == "organization.created" and event["organization_id"] == org["id"]
        for event in tenant_events
    )
    serialized = response.text + str(tenant_events)
    assert "sk-never-store-in-audit" not in serialized
    assert "openai_api_key" in serialized


async def test_audit_listing_is_isolated_by_current_organization(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    await _step_up(admin_client, "supersecret123")
    org_a = (await admin_client.post("/api/organizations", json={"name": "Org A"})).json()
    org_b = (await admin_client.post("/api/organizations", json={"name": "Org B"})).json()
    await _create_org_admin(admin_client, database, org_a["id"], "a-admin@example.com")
    await _create_org_admin(admin_client, database, org_b["id"], "b-admin@example.com")

    await _login(admin_client, "a-admin@example.com", "password123")
    await admin_client.put("/api/settings", json={"base_prompt": "A rules"})
    a_events = (await admin_client.get("/api/audit-events")).json()
    assert a_events
    assert {event["organization_id"] for event in a_events} == {org_a["id"]}

    await _login(admin_client, "b-admin@example.com", "password123")
    await admin_client.put("/api/settings", json={"base_prompt": "B rules"})
    b_events = (await admin_client.get("/api/audit-events")).json()
    assert b_events
    assert {event["organization_id"] for event in b_events} == {org_b["id"]}

    await _login(admin_client, "admin@example.com", "supersecret123")
    instance_events = (await admin_client.get("/api/audit-events")).json()
    assert all(event["organization_id"] is None for event in instance_events)
    assert not {org_a["id"], org_b["id"]} & {event["organization_id"] for event in instance_events}
    acting_events = (
        await admin_client.get("/api/audit-events", headers={"X-Acting-Org": str(org_a["id"])})
    ).json()
    assert acting_events
    assert {event["organization_id"] for event in acting_events} == {org_a["id"]}


async def test_regular_member_cannot_read_audit_log(
    admin_client: httpx.AsyncClient, database: Database
) -> None:
    await _step_up(admin_client, "supersecret123")
    org = (await admin_client.post("/api/organizations", json={"name": "Acme"})).json()
    await _step_up(admin_client, "supersecret123", int(org["id"]))
    created = await admin_client.post(
        "/api/users",
        json={"email": "member@example.com"},
        headers={"X-Acting-Org": str(org["id"])},
    )
    assert created.status_code == 201, created.text
    await set_test_user_password(database, "member@example.com")
    await _login(admin_client, "member@example.com", "password123")
    assert (await admin_client.get("/api/audit-events")).status_code == 403


async def test_entitlement_change_requires_step_up_and_is_audited(
    admin_client: httpx.AsyncClient,
) -> None:
    await _step_up(admin_client, "supersecret123")
    org = (await admin_client.post("/api/organizations", json={"name": "Acme"})).json()
    admin_client.cookies.delete(STEP_UP_COOKIE)
    denied = await admin_client.patch(f"/api/organizations/{org['id']}", json={"max_sites": 25})
    assert denied.status_code == 428

    await _step_up(admin_client, "supersecret123")
    updated = await admin_client.patch(f"/api/organizations/{org['id']}", json={"max_sites": 25})
    assert updated.status_code == 200, updated.text
    events = (
        await admin_client.get("/api/audit-events", headers={"X-Acting-Org": str(org["id"])})
    ).json()
    event = next(event for event in events if event["action"] == "organization.updated")
    assert event["details"]["changes"]["max_sites"] == {"from": None, "to": 25}


async def test_user_lifecycle_actions_are_audited(admin_client: httpx.AsyncClient) -> None:
    organization_id = int((await admin_client.get("/api/auth/me")).json()["organization_id"])
    await _step_up(admin_client, "supersecret123")
    created = await admin_client.post("/api/users", json={"email": "member@example.com"})
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    await _step_up(admin_client, "supersecret123")
    promoted = await admin_client.patch(f"/api/users/{user_id}", json={"is_admin": True})
    assert promoted.status_code == 200, promoted.text
    permissions = await admin_client.put(
        f"/api/users/{user_id}/permissions", json={"project_ids": [], "site_ids": []}
    )
    assert permissions.status_code == 200, permissions.text
    assert (await admin_client.delete(f"/api/users/{user_id}")).status_code == 204

    events = (
        await admin_client.get("/api/audit-events", headers={"X-Acting-Org": str(organization_id)})
    ).json()
    actions = [event["action"] for event in events if event["target_id"] == str(user_id)]
    assert actions == [
        "user.deleted",
        "user.permissions_updated",
        "user.updated",
        "user.created",
    ]


async def test_account_security_boundary_changes_are_audited(
    admin_client: httpx.AsyncClient,
) -> None:
    current = (await admin_client.get("/api/auth/me")).json()
    changed = await admin_client.post(
        "/api/auth/change-password",
        json={
            "current_password": "supersecret123",
            "new_password": "new-supersecret-456",
        },
    )
    assert changed.status_code == 204, changed.text

    await _step_up(admin_client, "new-supersecret-456")
    setup = await admin_client.post("/api/auth/totp/setup")
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    enabled = await admin_client.post(
        "/api/auth/totp/enable",
        json={"code": two_factor.generate_code(secret)},
    )
    assert enabled.status_code == 200, enabled.text
    recovery_code = enabled.json()["recovery_codes"][0]

    await admin_client.post("/api/auth/logout")
    password_step = await admin_client.post(
        "/api/auth/login",
        json={"email": current["email"], "password": "new-supersecret-456"},
    )
    assert password_step.status_code == 200, password_step.text
    assert password_step.json()["totp_required"] is True
    recovered = await admin_client.post("/api/auth/login/totp", json={"code": recovery_code})
    assert recovered.status_code == 200, recovered.text

    step_up = await admin_client.post(
        "/api/auth/step-up",
        json={
            "password": "new-supersecret-456",
            "totp_code": two_factor.generate_code(secret),
        },
    )
    assert step_up.status_code == 204, step_up.text
    assert (await admin_client.post("/api/auth/totp/disable")).status_code == 204

    events = (await admin_client.get("/api/audit-events", params={"limit": 200})).json()
    account_events = [
        event
        for event in events
        if event["target_type"] == "account" and event["target_id"] == str(current["id"])
    ]
    assert [event["action"] for event in account_events] == [
        "account.totp_disabled",
        "account.recovery_code_used",
        "account.totp_enabled",
        "account.password_changed",
    ]
    assert all(event["organization_id"] is None for event in account_events)


async def test_audit_model_rejects_updates_and_deletes(database: Database) -> None:
    async with database.session() as session:
        actor = User(
            email="actor@example.com",
            password_hash="not-used",
            is_admin=True,
            is_superadmin=True,
        )
        session.add(actor)
        await session.flush()
        event = AuditEvent(
            actor_user_id=actor.id,
            actor_email=actor.email,
            actor_is_superadmin=True,
            action="test.created",
            target_type="test",
            details={},
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    async with database.session() as session:
        event = await session.get(AuditEvent, event_id)
        assert event is not None
        event.target_label = "tampered"
        with pytest.raises(RuntimeError, match="append-only"):
            await session.commit()
        await session.rollback()

    async with database.session() as session:
        event = await session.get(AuditEvent, event_id)
        assert event is not None
        await session.delete(event)
        with pytest.raises(RuntimeError, match="append-only"):
            await session.commit()
        await session.rollback()


async def test_restore_event_survives_database_replacement(
    admin_client: httpx.AsyncClient,
) -> None:
    await _step_up(admin_client, "supersecret123")
    backup = await admin_client.get("/api/admin/backup")
    assert backup.status_code == 200
    before_restore = (await admin_client.get("/api/audit-events")).json()
    assert any(event["action"] == "backup.downloaded" for event in before_restore)
    restored = await admin_client.post(
        "/api/admin/restore",
        content=backup.content,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert restored.status_code == 200, restored.text
    login = await admin_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "supersecret123"},
    )
    assert login.status_code == 200
    events = (await admin_client.get("/api/audit-events")).json()
    assert any(event["action"] == "backup.restored" for event in events)
