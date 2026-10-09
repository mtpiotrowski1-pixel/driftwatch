"""Public sign-up creates an isolated, bounded organization without paid rights."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy import select

from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.models import Organization, Plan
from driftwatch.quota import ai_check_limit_reached
from driftwatch.security import two_factor


@pytest_asyncio.fixture
async def public_client(
    tmp_path: object,
    capturer: object,
    analyzer: object,
    channel: object,
    picker: object,
) -> AsyncIterator[httpx.AsyncClient]:
    """A client against a non-local (public) deployment: no first-account
    bootstrap, Secure cookies, and the multi-tenant sign-up rules in force."""
    from driftwatch.app import create_app

    settings = Settings(
        data_dir=str(tmp_path),
        database_url=f"sqlite+aiosqlite:///{tmp_path}/public.db",
        session_secret_key="public-session-key-0123456789-abcdef",
        encryption_key="public-encryption-key-0123456789-abcdef",
        scheduler_enabled=False,
        run_migrations=True,
        base_url="https://app.example.com",
        host="0.0.0.0",  # a public bind defeats is_local
        public_registration_enabled=True,
    )
    assert settings.is_local is False
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
        async with httpx.AsyncClient(transport=transport, base_url=settings.base_url) as client:
            yield client


async def test_public_registration_is_closed_by_default(
    tmp_path: object,
    capturer: object,
    analyzer: object,
    channel: object,
    picker: object,
) -> None:
    from driftwatch.app import create_app

    settings = Settings(
        data_dir=str(tmp_path),
        database_url=f"sqlite+aiosqlite:///{tmp_path}/closed-public.db",
        session_secret_key="closed-session-key-0123456789-abcdef",
        encryption_key="closed-encryption-key-0123456789-abcdef",
        scheduler_enabled=False,
        run_migrations=True,
        base_url="https://app.example.com",
        host="0.0.0.0",
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
        async with httpx.AsyncClient(transport=transport, base_url=settings.base_url) as client:
            capabilities = await client.get("/api/auth/capabilities")
            assert capabilities.status_code == 200
            assert capabilities.json() == {
                "registration_enabled": False,
                "initial_setup_required": False,
            }
            response = await client.post(
                "/api/auth/register",
                json={"email": "closed@example.com", "password": "password123"},
            )
            assert response.status_code == 403
            assert response.json()["detail"] == "Public registration is disabled"


async def test_public_signup_without_company_gets_its_own_isolated_org(
    public_client: httpx.AsyncClient,
) -> None:
    # On a public deploy nobody bootstraps as operator, and the shared
    # default-org join is disabled — each account gets its own isolated org, so a
    # stranger can never land inside (and read) another tenant's data.
    first = await public_client.post(
        "/api/auth/register", json={"email": "a@example.com", "password": "password123"}
    )
    assert first.status_code == 201
    assert first.json()["is_superadmin"] is False

    second = await public_client.post(
        "/api/auth/register", json={"email": "b@example.com", "password": "password123"}
    )
    assert second.status_code == 201
    assert second.json()["mfa_enrollment_required"] is True

    blocked = await public_client.get("/api/users")
    assert blocked.status_code == 428
    assert blocked.json()["detail"] == "MFA enrollment required"

    step_up = await public_client.post("/api/auth/step-up", json={"password": "password123"})
    assert step_up.status_code == 204, step_up.text
    setup = await public_client.post("/api/auth/totp/setup")
    assert setup.status_code == 200, setup.text
    enabled = await public_client.post(
        "/api/auth/totp/enable",
        json={"code": two_factor.generate_code(setup.json()["secret"])},
    )
    assert enabled.status_code == 200, enabled.text

    stepped = await public_client.post(
        "/api/auth/step-up",
        json={
            "password": "password123",
            "totp_code": two_factor.generate_code(setup.json()["secret"]),
        },
    )
    assert stepped.status_code == 204, stepped.text
    relay_attempt = await public_client.post(
        "/api/users", json={"email": "third-party-recipient@example.com"}
    )
    assert relay_attempt.status_code == 403
    assert "allows 1 member account" in relay_attempt.json()["detail"]

    # Now acting as b: their org holds only b — a@ is invisible across the tenant.
    emails = {u["email"] for u in (await public_client.get("/api/users")).json()}
    assert emails == {"b@example.com"}


async def test_signup_plan_intent_always_gets_the_same_bounded_free_entitlement(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    # Include legacy self-serve data to cover upgrades from deployments where
    # that flag could previously be enabled. Public registration must not copy
    # paid, self-serve, or unlimited caps even when the row already exists.
    async with database.session() as session:
        session.add_all(
            [
                Plan(
                    key="paid",
                    name="Paid",
                    max_sites=50,
                    monthly_ai_check_limit=5000,
                    price_override_cents=4900,
                    is_self_serve=False,
                ),
                Plan(
                    key="legacy-self-serve",
                    name="Legacy self-serve",
                    max_sites=7,
                    monthly_ai_check_limit=900,
                    price_override_cents=1900,
                    is_self_serve=True,
                ),
                Plan(
                    key="unlimited",
                    name="Unlimited",
                    max_sites=None,
                    monthly_ai_check_limit=None,
                    price_override_cents=9900,
                    is_self_serve=True,
                ),
            ]
        )
        await session.commit()

    admin_client.cookies.clear()
    intents = ["paid", "legacy-self-serve", "unlimited", "missing", None]
    for index, plan_key in enumerate(intents):
        payload = {
            "email": f"founder{index}@example.com",
            "password": "password123",
            "organization_name": f"Acme {index}",
        }
        if plan_key is not None:
            payload["plan_key"] = plan_key
        response = await admin_client.post("/api/auth/register", json=payload)
        assert response.status_code == 201, response.text
        assert response.json()["is_superadmin"] is False

    await admin_client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "supersecret123"}
    )
    orgs = {o["name"]: o for o in (await admin_client.get("/api/organizations")).json()}
    for index in range(len(intents)):
        org = orgs[f"Acme {index}"]
        assert org["plan"] == "free"
        assert org["plan_id"] is None
        assert org["max_sites"] == 1
        assert org["max_members"] == 1
        assert org["monthly_ai_check_limit"] == 0


async def test_signup_entitlement_enforces_one_site_and_zero_ai_checks(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    admin_client.cookies.clear()
    response = await admin_client.post(
        "/api/auth/register",
        json={
            "email": "bounded@example.com",
            "password": "password123",
            "organization_name": "Bounded",
            "plan_key": "unlimited",
        },
    )
    assert response.status_code == 201

    first = await admin_client.post("/api/sites", json={"url": "https://example.com/first"})
    second = await admin_client.post("/api/sites", json={"url": "https://example.org/second"})
    assert first.status_code == 201
    assert second.status_code == 403
    assert second.json()["detail"] == (
        "This workspace allows 1 monitored site(s). Contact an operator to request more access."
    )

    async with database.session() as session:
        organization = (
            await session.execute(select(Organization).where(Organization.name == "Bounded"))
        ).scalar_one()
        assert await ai_check_limit_reached(session, organization.id) is True


async def test_signup_rate_limit_caps_org_creation_per_ip(
    admin_client: httpx.AsyncClient,
) -> None:
    admin_client.cookies.clear()
    statuses = []
    for index in range(7):  # the per-IP cap is 5
        res = await admin_client.post(
            "/api/auth/register",
            json={
                "email": f"user{index}@example.com",
                "password": "password123",
                "organization_name": f"Co {index}",
            },
        )
        statuses.append(res.status_code)
    assert statuses.count(201) == 5
    assert statuses.count(429) == 2


async def test_register_existence_probe_is_rate_limited(
    admin_client: httpx.AsyncClient,
) -> None:
    # admin@example.com already exists (the bootstrap operator). Hammering register
    # with a known address must not stay an unthrottled account-enumeration oracle:
    # the 409s that confirm existence are capped per IP, then turn into 429s.
    statuses = [
        (
            await admin_client.post(
                "/api/auth/register",
                json={"email": "admin@example.com", "password": "password123"},
            )
        ).status_code
        for _ in range(13)
    ]

    assert 409 in statuses  # existence is reported at first...
    assert 429 in statuses  # ...but only until the per-IP probe ceiling trips
    assert statuses[-1] == 429  # and once throttled it stays shut
