"""End-to-end tests for the two-factor login flow over the API."""

from __future__ import annotations

import httpx

from driftwatch.config import Settings
from driftwatch.models import Organization, User
from driftwatch.security import two_factor
from driftwatch.security.passwords import ahash_password
from tests.conftest import FakePicker, RecordingChannel, ScriptedCapturer, StubAnalyzer


async def _register(client: httpx.AsyncClient, email: str = "user@example.com") -> None:
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": "password123"}
    )
    assert response.status_code == 201, response.text


async def _step_up(
    client: httpx.AsyncClient,
    *,
    password: str = "password123",
    code: str | None = None,
) -> None:
    payload: dict[str, str] = {"password": password}
    if code is not None:
        payload["totp_code"] = code
    response = await client.post("/api/auth/step-up", json=payload)
    assert response.status_code == 204, response.text


async def _enroll(client: httpx.AsyncClient) -> tuple[str, list[str]]:
    """Enable 2FA for the logged-in account; return (secret, recovery_codes)."""
    await _step_up(client)
    setup = await client.post("/api/auth/totp/setup")
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert setup.json()["qr_svg_data_uri"].startswith("data:image/svg+xml")

    enable = await client.post(
        "/api/auth/totp/enable", json={"code": two_factor.generate_code(secret)}
    )
    assert enable.status_code == 200, enable.text
    codes = enable.json()["recovery_codes"]
    assert len(codes) == 10
    return secret, codes


async def test_local_privileged_account_is_not_forced_to_enroll_mfa(
    client: httpx.AsyncClient,
) -> None:
    await _register(client)
    me = await client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["is_admin"] is True
    assert me.json()["is_superadmin"] is True
    assert me.json()["mfa_enrollment_required"] is False
    assert (await client.get("/api/organizations")).status_code == 200


async def test_enroll_then_login_requires_code(client: httpx.AsyncClient) -> None:
    await _register(client)
    secret, _ = await _enroll(client)
    assert (await client.get("/api/auth/me")).json()["totp_enabled"] is True

    await client.post("/api/auth/logout")
    # Correct password alone yields a challenge, not a session.
    first = await client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "password123"}
    )
    assert first.status_code == 200
    assert first.json() == {"totp_required": True, "user": None}
    assert (await client.get("/api/auth/me")).status_code == 401

    # A wrong code is refused; the right one completes the login.
    assert (await client.post("/api/auth/login/totp", json={"code": "000000"})).status_code == 401
    done = await client.post(
        "/api/auth/login/totp", json={"code": two_factor.generate_code(secret)}
    )
    assert done.status_code == 200
    assert (await client.get("/api/auth/me")).json()["email"] == "user@example.com"


async def test_totp_issuer_follows_the_brand_name(client: httpx.AsyncClient) -> None:
    # The authenticator-app label is the configured brand, not the stock name.
    await _register(client)  # first account on a local deploy is the operator
    update = await client.put("/api/settings", json={"brand_name": "Acme Watch"})
    assert update.status_code == 200, update.text
    await _step_up(client)
    setup = await client.post("/api/auth/totp/setup")
    assert setup.status_code == 200, setup.text
    assert "issuer=Acme%20Watch" in setup.json()["otpauth_uri"]


async def test_totp_code_step_requires_pending_login(client: httpx.AsyncClient) -> None:
    await _register(client)
    secret, _ = await _enroll(client)
    await client.post("/api/auth/logout")
    # No password step first → no pending cookie → the code endpoint refuses.
    assert (
        await client.post("/api/auth/login/totp", json={"code": two_factor.generate_code(secret)})
    ).status_code == 401


async def test_recovery_code_logs_in_and_is_single_use(client: httpx.AsyncClient) -> None:
    await _register(client)
    _, codes = await _enroll(client)
    await client.post("/api/auth/logout")

    await client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "password123"}
    )
    first = await client.post("/api/auth/login/totp", json={"code": codes[0]})
    assert first.status_code == 200

    # The same recovery code cannot be reused.
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "password123"}
    )
    reused = await client.post("/api/auth/login/totp", json={"code": codes[0]})
    assert reused.status_code == 401
    fresh = await client.post("/api/auth/login/totp", json={"code": codes[1]})
    assert fresh.status_code == 200


async def test_disable_requires_password_and_clears_2fa(client: httpx.AsyncClient) -> None:
    await _register(client)
    secret, _ = await _enroll(client)

    assert (await client.post("/api/auth/totp/disable")).status_code == 428
    assert (await client.post("/api/auth/step-up", json={"password": "wrong"})).status_code == 400
    await _step_up(client, code=two_factor.generate_code(secret))
    assert (await client.post("/api/auth/totp/disable")).status_code == 204
    assert (await client.get("/api/auth/me")).json()["totp_enabled"] is False

    # With 2FA off, the password alone logs in again.
    await client.post("/api/auth/logout")
    again = await client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "password123"}
    )
    assert again.status_code == 200
    assert again.json()["user"]["email"] == "user@example.com"


async def test_totp_enable_and_disable_attempts_are_throttled(
    client: httpx.AsyncClient,
) -> None:
    await _register(client)
    await _step_up(client)
    setup = await client.post("/api/auth/totp/setup")
    assert setup.status_code == 200
    valid = two_factor.generate_code(setup.json()["secret"])
    invalid = "000000" if valid != "000000" else "000001"
    enable_statuses = [
        (await client.post("/api/auth/totp/enable", json={"code": invalid})).status_code
        for _ in range(11)
    ]
    assert enable_statuses[:10] == [400] * 10
    assert enable_statuses[10] == 429


async def test_totp_disable_step_up_attempts_are_throttled(client: httpx.AsyncClient) -> None:
    await _register(client)
    await _enroll(client)
    statuses = [
        (await client.post("/api/auth/step-up", json={"password": "wrong"})).status_code
        for _ in range(11)
    ]
    assert statuses[:10] == [400] * 10
    assert statuses[10] == 429


async def test_setup_conflicts_once_enabled(client: httpx.AsyncClient) -> None:
    await _register(client)
    secret, _ = await _enroll(client)
    await _step_up(client, code=two_factor.generate_code(secret))
    assert (await client.post("/api/auth/totp/setup")).status_code == 409


async def test_enabling_2fa_revokes_pre_enrollment_session(client: httpx.AsyncClient) -> None:
    await _register(client)
    original_session = client.cookies.get("driftwatch_session")
    assert original_session

    await _enroll(client)

    response = await client.get(
        "/api/auth/me",
        headers={"Cookie": f"driftwatch_session={original_session}"},
    )
    assert response.status_code == 401
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_public_superadmin_is_confined_until_mfa_is_enrolled(
    tmp_path: object,
    capturer: ScriptedCapturer,
    analyzer: StubAnalyzer,
    channel: RecordingChannel,
    picker: FakePicker,
) -> None:
    from driftwatch.app import create_app

    settings = Settings(
        data_dir=str(tmp_path),
        database_url=f"sqlite+aiosqlite:///{tmp_path}/public.db",
        session_secret_key="public-session-key-0123456789-abcdef",
        encryption_key="public-encryption-key-0123456789-abcdef",
        host="0.0.0.0",
        base_url="https://driftwatch.example.com",
        scheduler_enabled=False,
        run_migrations=True,
        initial_admin_email="operator@example.com",
        initial_admin_password="strong-password-123",
    )
    app = create_app(
        settings,
        capturer=capturer,
        analyzer=analyzer,
        channel=channel,
        picker=picker,
        enable_scheduler=False,
    )

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=settings.base_url) as public:
            login = await public.post(
                "/api/auth/login",
                json={
                    "email": "operator@example.com",
                    "password": "strong-password-123",
                },
            )
            assert login.status_code == 200, login.text
            assert login.json()["user"]["mfa_enrollment_required"] is True

            me = await public.get("/api/auth/me")
            assert me.status_code == 200, me.text
            assert me.json()["mfa_enrollment_required"] is True
            own_headers = {"X-Acting-Org": str(login.json()["user"]["organization_id"])}
            owned = await public.get("/api/auth/me", headers=own_headers)
            assert owned.status_code == 200, owned.text
            assert owned.json()["acting_organization_id"] == login.json()["user"]["organization_id"]
            for context in ("0", "999", "invalid"):
                assert (
                    await public.get("/api/auth/me", headers={"X-Acting-Org": context})
                ).status_code == 428

            for path in ("/api/sites", "/api/organizations", "/api/operators"):
                blocked = await public.get(path)
                assert blocked.status_code == 428
                assert blocked.json()["detail"] == "MFA enrollment required"

            assert (await public.post("/api/auth/totp/setup")).status_code == 428
            step_up = await public.post(
                "/api/auth/step-up",
                json={"password": "strong-password-123"},
            )
            assert step_up.status_code == 204, step_up.text
            setup = await public.post("/api/auth/totp/setup")
            assert setup.status_code == 200, setup.text
            enabled = await public.post(
                "/api/auth/totp/enable",
                json={"code": two_factor.generate_code(setup.json()["secret"])},
            )
            assert enabled.status_code == 200, enabled.text

            assert (await public.get("/api/auth/me")).json()["mfa_enrollment_required"] is False
            sites = await public.get("/api/sites")
            assert sites.status_code == 400, sites.text
            for path in ("/api/organizations", "/api/operators"):
                response = await public.get(path)
                assert response.status_code == 200, f"{path}: {response.text}"


async def test_public_suspended_org_admin_can_enroll_required_mfa(
    tmp_path: object,
    capturer: ScriptedCapturer,
    analyzer: StubAnalyzer,
    channel: RecordingChannel,
    picker: FakePicker,
) -> None:
    from driftwatch.app import create_app

    password = "org-admin-password-123"
    settings = Settings(
        data_dir=str(tmp_path),
        database_url=f"sqlite+aiosqlite:///{tmp_path}/public-org-admin.db",
        session_secret_key="public-admin-session-key-0123456789-abcdef",
        encryption_key="public-admin-encryption-key-0123456789-abcdef",
        host="0.0.0.0",
        base_url="https://driftwatch.example.com",
        scheduler_enabled=False,
        run_migrations=True,
        initial_admin_email="operator@example.com",
        initial_admin_password="strong-password-123",
    )
    app = create_app(
        settings,
        capturer=capturer,
        analyzer=analyzer,
        channel=channel,
        picker=picker,
        enable_scheduler=False,
    )

    async with app.router.lifespan_context(app):
        async with app.state.db.session() as session:
            organization = Organization(name="Suspended customer", is_active=False)
            session.add(organization)
            await session.flush()
            session.add(
                User(
                    email="org-admin@example.com",
                    name="Organization admin",
                    password_hash=await ahash_password(password),
                    organization_id=organization.id,
                    is_admin=True,
                    is_superadmin=False,
                )
            )
            await session.commit()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=settings.base_url) as public:
            login = await public.post(
                "/api/auth/login",
                json={"email": "org-admin@example.com", "password": password},
            )
            assert login.status_code == 200, login.text
            assert login.json()["user"]["mfa_enrollment_required"] is True
            assert login.json()["user"]["organization_suspended"] is True

            me = await public.get("/api/auth/me")
            assert me.status_code == 200, me.text
            assert me.json()["mfa_enrollment_required"] is True
            assert me.json()["organization_suspended"] is True

            blocked = await public.get("/api/sites")
            assert blocked.status_code == 428
            assert blocked.json()["detail"] == "MFA enrollment required"
            assert (await public.get("/api/billing/status")).status_code == 428

            assert (await public.post("/api/auth/totp/setup")).status_code == 428
            step_up = await public.post(
                "/api/auth/step-up",
                json={"password": password},
            )
            assert step_up.status_code == 204, step_up.text
            setup = await public.post("/api/auth/totp/setup")
            assert setup.status_code == 200, setup.text
            enabled = await public.post(
                "/api/auth/totp/enable",
                json={"code": two_factor.generate_code(setup.json()["secret"])},
            )
            assert enabled.status_code == 200, enabled.text

            enrolled = await public.get("/api/auth/me")
            assert enrolled.status_code == 200, enrolled.text
            assert enrolled.json()["mfa_enrollment_required"] is False
            assert enrolled.json()["organization_suspended"] is True
            assert (await public.get("/api/sites")).status_code == 403
