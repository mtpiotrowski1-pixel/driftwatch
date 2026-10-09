from __future__ import annotations

import httpx
import pytest

import driftwatch.api.operators as operators_api
from driftwatch.api.deps import STEP_UP_COOKIE
from driftwatch.db import Database
from driftwatch.models import User
from driftwatch.security.passwords import ahash_password

_PASSWORD = "supersecret123"


async def _step_up(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/auth/step-up", json={"password": _PASSWORD})
    assert response.status_code == 204, response.text


async def _seed_operator(database: Database, email: str) -> int:
    async with database.session() as session:
        operator = User(
            email=email,
            name="Recovery operator",
            password_hash=await ahash_password("recovery-password"),
            organization_id=None,
            is_admin=True,
            is_superadmin=True,
        )
        session.add(operator)
        await session.commit()
        return operator.id


@pytest.fixture
def queued_invitations(
    monkeypatch: pytest.MonkeyPatch,
) -> list[int]:
    queued: list[int] = []

    async def enqueue(*_: object, user: User, **__: object) -> None:
        queued.append(user.id)

    monkeypatch.setattr(operators_api, "enqueue_account_invitation", enqueue)
    return queued


async def test_operator_list_is_superadmin_only_and_instance_scoped(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    current = (await admin_client.get("/api/auth/me")).json()
    listed = await admin_client.get("/api/operators")
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [current["id"]]

    acting = await admin_client.get(
        "/api/operators",
        headers={"X-Acting-Org": str(current["organization_id"])},
    )
    assert acting.status_code == 409
    assert acting.json()["detail"] == (
        "Exit the active organization before managing instance resources"
    )

    async with database.session() as session:
        session.add(
            User(
                email="org-admin@example.com",
                name="Organization admin",
                password_hash=await ahash_password("org-admin-password"),
                organization_id=int(current["organization_id"]),
                is_admin=True,
                is_superadmin=False,
            )
        )
        await session.commit()
    await admin_client.post("/api/auth/logout")
    login = await admin_client.post(
        "/api/auth/login",
        json={"email": "org-admin@example.com", "password": "org-admin-password"},
    )
    assert login.status_code == 200, login.text
    assert (await admin_client.get("/api/operators")).status_code == 403


async def test_operator_creation_is_step_up_gated_audited_and_has_no_delete_route(
    admin_client: httpx.AsyncClient,
    database: Database,
    queued_invitations: list[int],
) -> None:
    payload = {"email": "recovery@example.com", "name": "Recovery"}
    assert (await admin_client.post("/api/operators", json=payload)).status_code == 428

    await _step_up(admin_client)
    created = await admin_client.post("/api/operators", json=payload)
    assert created.status_code == 201, created.text
    operator = created.json()
    assert operator["email"] == "recovery@example.com"
    assert operator["is_active"] is True
    assert operator["totp_enabled"] is False
    assert queued_invitations == [operator["id"]]

    async with database.session() as session:
        persisted = await session.get(User, operator["id"])
        assert persisted is not None
        assert persisted.organization_id is None
        assert persisted.is_admin is True
        assert persisted.is_superadmin is True

    events = (await admin_client.get("/api/audit-events")).json()
    event = next(row for row in events if row["action"] == "operator.created")
    assert event["target_id"] == str(operator["id"])
    assert event["organization_id"] is None
    assert event["details"] == {"invitation_delivery": "scheduled"}

    assert (await admin_client.delete(f"/api/operators/{operator['id']}")).status_code == 405
    demotion = await admin_client.patch(
        f"/api/operators/{operator['id']}",
        json={"is_superadmin": False},
    )
    assert demotion.status_code == 422


async def test_operator_lifecycle_protects_self_and_last_active_identity(
    admin_client: httpx.AsyncClient,
    database: Database,
    queued_invitations: list[int],
) -> None:
    current_id = int((await admin_client.get("/api/auth/me")).json()["id"])
    await _step_up(admin_client)

    last_active = await admin_client.patch(
        f"/api/operators/{current_id}", json={"is_active": False}
    )
    assert last_active.status_code == 400
    assert last_active.json()["detail"] == "The last active operator cannot be deactivated"

    recovery_id = await _seed_operator(database, "second-operator@example.com")
    self_deactivate = await admin_client.patch(
        f"/api/operators/{current_id}", json={"is_active": False}
    )
    assert self_deactivate.status_code == 400
    assert self_deactivate.json()["detail"] == "You cannot deactivate yourself"

    admin_client.cookies.delete(STEP_UP_COOKIE)
    denied = await admin_client.patch(
        f"/api/operators/{recovery_id}", json={"name": "Recovery owner"}
    )
    assert denied.status_code == 428
    await _step_up(admin_client)

    renamed = await admin_client.patch(
        f"/api/operators/{recovery_id}",
        json={"name": "Recovery owner", "email": "recovery-owner@example.com"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["email"] == "recovery-owner@example.com"

    deactivated = await admin_client.patch(
        f"/api/operators/{recovery_id}", json={"is_active": False}
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["is_active"] is False
    inactive_invite = await admin_client.post(f"/api/operators/{recovery_id}/invite")
    assert inactive_invite.status_code == 409

    reactivated = await admin_client.patch(
        f"/api/operators/{recovery_id}", json={"is_active": True}
    )
    assert reactivated.status_code == 200, reactivated.text

    admin_client.cookies.delete(STEP_UP_COOKIE)
    denied_invite = await admin_client.post(f"/api/operators/{recovery_id}/invite")
    assert denied_invite.status_code == 428
    await _step_up(admin_client)
    invited = await admin_client.post(f"/api/operators/{recovery_id}/invite")
    assert invited.status_code == 204, invited.text
    assert queued_invitations == [recovery_id]

    events = (await admin_client.get("/api/audit-events")).json()
    updated = [
        row
        for row in events
        if row["action"] == "operator.updated" and row["target_id"] == str(recovery_id)
    ]
    assert len(updated) == 3
    invitation = next(
        row
        for row in events
        if row["action"] == "operator.invitation_queued" and row["target_id"] == str(recovery_id)
    )
    assert invitation["details"] == {"delivery": "scheduled"}


async def test_operator_recovery_actions_are_step_up_gated_and_audited(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    operator_id = await _seed_operator(database, "compromised-operator@example.com")
    async with database.session() as session:
        operator = await session.get(User, operator_id)
        assert operator is not None
        operator.totp_enabled = True
        operator.totp_secret = "encrypted-placeholder"
        operator.recovery_code_hashes = ["recovery-hash"]
        original_version = operator.token_version
        await session.commit()

    revoke_path = f"/api/operators/{operator_id}/revoke-sessions"
    reset_path = f"/api/operators/{operator_id}/reset-totp"
    assert (await admin_client.post(revoke_path)).status_code == 428
    assert (await admin_client.post(reset_path)).status_code == 428

    await _step_up(admin_client)
    revoked = await admin_client.post(revoke_path)
    assert revoked.status_code == 204, revoked.text

    reset = await admin_client.post(reset_path)
    assert reset.status_code == 204, reset.text

    async with database.session() as session:
        operator = await session.get(User, operator_id)
        assert operator is not None
        assert operator.totp_enabled is False
        assert operator.totp_secret is None
        assert operator.recovery_code_hashes == []
        assert operator.token_version == original_version + 2

    events = (await admin_client.get("/api/audit-events")).json()
    actions = {
        row["action"]
        for row in events
        if row["target_type"] == "operator" and row["target_id"] == str(operator_id)
    }
    assert {"operator.sessions_revoked", "operator.totp_reset"} <= actions


async def test_operator_can_emergency_revoke_own_sessions(
    admin_client: httpx.AsyncClient,
) -> None:
    current_id = int((await admin_client.get("/api/auth/me")).json()["id"])
    await _step_up(admin_client)

    revoked = await admin_client.post(f"/api/operators/{current_id}/revoke-sessions")
    assert revoked.status_code == 204, revoked.text
    assert (await admin_client.get("/api/auth/me")).status_code == 401
