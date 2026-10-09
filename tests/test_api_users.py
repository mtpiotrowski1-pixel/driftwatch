"""Editing an existing user: profile fields and email uniqueness."""

from __future__ import annotations

import re

import httpx
import jwt
import pytest
from sqlalchemy import select

from driftwatch.account_mail import AccountEmailWorker
from driftwatch.api.deps import STEP_UP_COOKIE
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.models import BillingPrice, CheckoutAttempt, Plan, Setting, User
from driftwatch.schemas import UserCreate
from driftwatch.security.passwords import ahash_password, averify_password
from driftwatch.security.tokens import PURPOSE_PASSWORD_RESET, read_scoped_token
from tests.conftest import RecordingChannel


async def _step_up(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/auth/step-up", json={"password": "supersecret123"})
    assert response.status_code == 204, response.text


async def _create(client: httpx.AsyncClient, email: str, name: str | None = None) -> int:
    await _step_up(client)
    body: dict[str, object] = {"email": email}
    if name is not None:
        body["name"] = name
    created = await client.post("/api/users", json=body)
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


async def _current_tenant_audit(client: httpx.AsyncClient) -> list[dict[str, object]]:
    organization_id = int((await client.get("/api/auth/me")).json()["organization_id"])
    response = await client.get("/api/audit-events", headers={"X-Acting-Org": str(organization_id)})
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


async def _set_test_password(database: Database, user_id: int) -> None:
    """Give a fixture account a known credential without restoring an admin API."""
    async with database.session() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.password_hash = await ahash_password("password123")
        await session.commit()


def _token_from_invitation(channel: RecordingChannel) -> str:
    match = re.search(r"/reset-password#token=([^\s]+)", channel.sent[-1].text_body)
    assert match is not None
    return match.group(1)


def test_user_create_schema_does_not_expose_a_password() -> None:
    assert "password" not in UserCreate.model_json_schema()["properties"]


async def test_create_rejects_legacy_admin_selected_password(
    admin_client: httpx.AsyncClient,
) -> None:
    response = await admin_client.post(
        "/api/users",
        json={
            "email": "legacy-client@example.com",
            "password": "administrator-chosen-password",
        },
    )

    assert response.status_code == 422


async def test_create_requires_step_up_and_sends_single_use_invitation(
    admin_client: httpx.AsyncClient,
    channel: RecordingChannel,
    database: Database,
    settings: Settings,
) -> None:
    # A value left by an older release must never redirect a secret-bearing
    # invitation. BASE_URL from deployment configuration is authoritative.
    async with database.session() as session:
        session.add(Setting(key="app_base_url", value="https://attacker.example"))
        await session.commit()
    body = {
        "email": "invitee@example.com",
        "name": "Invitee",
    }

    denied = await admin_client.post("/api/users", json=body)
    assert denied.status_code == 428
    assert not channel.sent

    await _step_up(admin_client)
    created = await admin_client.post("/api/users", json=body)
    assert created.status_code == 201, created.text
    assert channel.sent == []
    assert await AccountEmailWorker(database, settings, channel=channel).drain() == 1
    assert len(channel.sent) == 1
    assert channel.sent[0].to == "invitee@example.com"
    assert "24 hours" in channel.sent[0].text_body
    assert settings.base_url in channel.sent[0].text_body
    assert "attacker.example" not in channel.sent[0].text_body

    user_id = int(created.json()["id"])
    token = _token_from_invitation(channel)
    claims = read_scoped_token(
        token,
        secret=settings.token_secrets,
        purpose=PURPOSE_PASSWORD_RESET,
    )
    raw_claims = jwt.decode(token, settings.token_secret, algorithms=["HS256"])
    assert raw_claims["exp"] - raw_claims["iat"] == 24 * 60 * 60

    async with database.session() as session:
        user = await session.get(User, user_id)
        assert user is not None
        assert claims.user_id == user.id
        assert claims.token_version == user.token_version
        assert claims.session_generation == user.session_generation
        assert not await averify_password("known-password", user.password_hash)

    events = await _current_tenant_audit(admin_client)
    created_event = next(
        event
        for event in events
        if event["action"] == "user.created" and event["target_id"] == str(user_id)
    )
    assert created_event["details"] == {
        "is_admin": False,
        "invitation_delivery": "scheduled",
    }
    assert token not in str(created_event)

    consumed = await admin_client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "invitee-owned-password"},
    )
    replayed = await admin_client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "replayed-password"},
    )
    assert consumed.status_code == 204
    assert replayed.status_code == 400
    login = await admin_client.post(
        "/api/auth/login",
        json={"email": "invitee@example.com", "password": "invitee-owned-password"},
    )
    assert login.status_code == 200, login.text


async def test_resending_invitation_is_step_up_gated_and_rate_limited(
    admin_client: httpx.AsyncClient,
    channel: RecordingChannel,
    database: Database,
    settings: Settings,
) -> None:
    user_id = await _create(admin_client, "resend@example.com")
    worker = AccountEmailWorker(database, settings, channel=channel)
    assert await worker.drain() == 1
    assert len(channel.sent) == 1

    admin_client.cookies.delete(STEP_UP_COOKIE)
    denied = await admin_client.post(f"/api/users/{user_id}/invite")
    assert denied.status_code == 428
    await _step_up(admin_client)

    statuses: list[int] = []
    for _ in range(4):
        response = await admin_client.post(f"/api/users/{user_id}/invite")
        statuses.append(response.status_code)
        if response.status_code == 204:
            assert await worker.drain() == 1
    assert statuses == [204, 204, 204, 429]
    assert len(channel.sent) == 4
    events = await _current_tenant_audit(admin_client)
    invitation_events = [
        event
        for event in events
        if event["action"] == "user.invitation_queued" and event["target_id"] == str(user_id)
    ]
    assert len(invitation_events) == 3
    assert all(event["details"] == {"delivery": "scheduled"} for event in invitation_events)
    assert all("#token=" not in str(event) for event in invitation_events)


@pytest.mark.parametrize(
    ("frontend_bundle", "expected_status"),
    [(False, 404), (True, 405)],
    indirect=["frontend_bundle"],
    ids=["api-only", "with-spa"],
)
async def test_manual_admin_password_endpoint_is_removed(
    admin_client: httpx.AsyncClient,
    database: Database,
    expected_status: int,
) -> None:
    user_id = await _create(admin_client, "no-takeover@example.com")
    async with database.session() as session:
        user = await session.get(User, user_id)
        assert user is not None
        credentials_before = (user.password_hash, user.token_version, user.session_generation)

    response = await admin_client.post(
        f"/api/users/{user_id}/password",
        json={"new_password": "administrator-chosen-password"},
    )
    assert response.status_code == expected_status
    assert "application/json" in response.headers["content-type"]
    assert response.json()["detail"] == (
        "Not Found" if expected_status == 404 else "Method Not Allowed"
    )
    async with database.session() as session:
        user = await session.get(User, user_id)
        assert user is not None
        assert (
            user.password_hash,
            user.token_version,
            user.session_generation,
        ) == credentials_before
        assert not await averify_password("administrator-chosen-password", user.password_hash)


async def test_admin_edits_user_name_and_email(admin_client: httpx.AsyncClient) -> None:
    user_id = await _create(admin_client, "one@example.com", name="One")
    await _step_up(admin_client)
    patched = await admin_client.patch(
        f"/api/users/{user_id}", json={"name": "Renamed", "email": "renamed@example.com"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Renamed"
    assert patched.json()["email"] == "renamed@example.com"


async def test_editing_to_a_taken_email_conflicts(admin_client: httpx.AsyncClient) -> None:
    first = await _create(admin_client, "a@example.com")
    await _create(admin_client, "b@example.com")
    await _step_up(admin_client)
    conflict = await admin_client.patch(f"/api/users/{first}", json={"email": "b@example.com"})
    assert conflict.status_code == 409, conflict.text


async def test_admin_can_toggle_role_and_status(admin_client: httpx.AsyncClient) -> None:
    user_id = await _create(admin_client, "member@example.com")
    await _step_up(admin_client)
    promoted = await admin_client.patch(f"/api/users/{user_id}", json={"is_admin": True})
    assert promoted.status_code == 200 and promoted.json()["is_admin"] is True
    deactivated = await admin_client.patch(f"/api/users/{user_id}", json={"is_active": False})
    assert deactivated.status_code == 200 and deactivated.json()["is_active"] is False


async def test_sensitive_account_edit_revokes_existing_sessions(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    user_id = await _create(admin_client, "member-session@example.com")
    await _set_test_password(database, user_id)
    await admin_client.post("/api/auth/logout")
    login = await admin_client.post(
        "/api/auth/login",
        json={"email": "member-session@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    member_session = admin_client.cookies.get("driftwatch_session")
    assert member_session

    await admin_client.post("/api/auth/logout")
    admin_login = await admin_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "supersecret123"},
    )
    assert admin_login.status_code == 200, admin_login.text
    await _step_up(admin_client)
    patched = await admin_client.patch(
        f"/api/users/{user_id}",
        json={"email": "member-session-renamed@example.com"},
    )
    assert patched.status_code == 200, patched.text

    stale = await admin_client.get(
        "/api/auth/me",
        headers={"Cookie": f"driftwatch_session={member_session}"},
    )
    assert stale.status_code == 401
    assert stale.json()["detail"] == "Session has been revoked"


async def test_admin_can_revoke_all_user_sessions(
    admin_client: httpx.AsyncClient, database: Database
) -> None:
    user_id = await _create(admin_client, "revoke-me@example.com")
    await _set_test_password(database, user_id)
    await admin_client.post("/api/auth/logout")
    login = await admin_client.post(
        "/api/auth/login",
        json={"email": "revoke-me@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    member_session = admin_client.cookies.get("driftwatch_session")
    assert member_session

    await admin_client.post("/api/auth/logout")
    await admin_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "supersecret123"},
    )
    await _step_up(admin_client)
    revoked = await admin_client.post(f"/api/users/{user_id}/revoke-sessions")
    assert revoked.status_code == 204, revoked.text

    stale = await admin_client.get(
        "/api/auth/me",
        headers={"Cookie": f"driftwatch_session={member_session}"},
    )
    assert stale.status_code == 401


async def test_admin_can_reset_user_totp_and_revokes_sessions(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    user_id = await _create(admin_client, "lost-factor@example.com")
    async with database.session() as session:
        target = await session.get(User, user_id)
        assert target is not None
        previous_version = target.token_version
        target.totp_enabled = True
        target.totp_secret = "encrypted-placeholder"
        target.recovery_code_hashes = ["recovery-hash"]
        await session.commit()

    await _step_up(admin_client)
    reset = await admin_client.post(f"/api/users/{user_id}/reset-totp")
    assert reset.status_code == 204, reset.text

    async with database.session() as session:
        target = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        assert target.totp_enabled is False
        assert target.totp_secret is None
        assert target.recovery_code_hashes == []
        assert target.token_version == previous_version + 1


async def test_user_with_checkout_history_must_be_deactivated_not_deleted(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    user_id = await _create(admin_client, "billing-history@example.com")
    async with database.session() as session:
        user = await session.get(User, user_id)
        assert user is not None and user.organization_id is not None
        plan = Plan(
            key="retained-user-plan",
            name="Retained user plan",
            max_sites=5,
            monthly_ai_check_limit=50,
            currency="USD",
        )
        session.add(plan)
        await session.flush()
        price = BillingPrice(
            plan_id=plan.id,
            provider="stripe",
            provider_price_id="price_retained_user",
            version=1,
            unit_amount_minor=1_000,
            currency="USD",
            recurring_interval="month",
            interval_count=1,
        )
        session.add(price)
        await session.flush()
        session.add(
            CheckoutAttempt(
                organization_id=user.organization_id,
                billing_price_id=price.id,
                requested_by_user_id=user.id,
                idempotency_key="retained-user-checkout",
                terms_version="terms-1",
                privacy_version="privacy-1",
                status="failed",
                active_marker=None,
            )
        )
        await session.commit()

    await _step_up(admin_client)
    response = await admin_client.delete(f"/api/users/{user_id}")

    assert response.status_code == 409
    assert "deactivated" in response.json()["detail"]
    async with database.session() as session:
        assert await session.get(User, user_id) is not None
