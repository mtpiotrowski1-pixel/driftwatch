"""Plan limits: site quota, monthly AI cap, organization suspension, and the fact
that only the operator — never a customer's own admin — can change any of them."""

from __future__ import annotations

import httpx
from tests.conftest import create_org, set_test_user_password

from driftwatch.db import Database
from driftwatch.models import AIUsage, Organization, Site
from driftwatch.quota import ai_check_limit_reached


async def _step_up(admin_client: httpx.AsyncClient, organization_id: int | None = None) -> None:
    headers = {"X-Acting-Org": str(organization_id)} if organization_id is not None else None
    response = await admin_client.post(
        "/api/auth/step-up",
        headers=headers,
        json={"password": "supersecret123"},
    )
    assert response.status_code == 204, response.text


async def _org(admin_client: httpx.AsyncClient, name: str, **fields: object) -> dict:
    await _step_up(admin_client)
    org = (await admin_client.post("/api/organizations", json={"name": name})).json()
    if fields:
        org = (await admin_client.patch(f"/api/organizations/{org['id']}", json=fields)).json()
    return org


async def test_site_limit_is_enforced(admin_client: httpx.AsyncClient) -> None:
    org = await _org(admin_client, "Capped", max_sites=1)
    headers = {"X-Acting-Org": str(org["id"])}
    first = await admin_client.post(
        "/api/sites", json={"url": "https://example.com/1"}, headers=headers
    )
    second = await admin_client.post(
        "/api/sites", json={"url": "https://example.org/2"}, headers=headers
    )
    assert first.status_code == 201
    assert second.status_code == 403  # plan limit reached


async def test_organization_out_exposes_plan_and_usage(admin_client: httpx.AsyncClient) -> None:
    org = await _org(
        admin_client, "Plans", plan="business", max_sites=5, monthly_ai_check_limit=1000
    )
    listed = {o["id"]: o for o in (await admin_client.get("/api/organizations")).json()}
    me = listed[org["id"]]
    assert me["plan"] == "business"
    assert me["max_sites"] == 5
    assert me["monthly_ai_check_limit"] == 1000
    assert me["ai_checks_this_month"] == 0


async def test_suspended_org_locks_out_members_but_not_operator(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    org = await _org(admin_client, "Suspendable")
    headers = {"X-Acting-Org": str(org["id"])}
    await _step_up(admin_client, int(org["id"]))
    created = await admin_client.post(
        "/api/users",
        json={"email": "client-admin@example.com", "is_admin": True},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    await set_test_user_password(database, "client-admin@example.com")

    # The org-admin works while the org is active.
    await admin_client.post(
        "/api/auth/login", json={"email": "client-admin@example.com", "password": "password123"}
    )
    assert (await admin_client.get("/api/auth/me")).status_code == 200

    # The operator suspends the org.
    await admin_client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "supersecret123"}
    )
    await _step_up(admin_client)
    suspended = await admin_client.patch(
        f"/api/organizations/{org['id']}", json={"is_active": False}
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["is_active"] is False

    # The suspended org can authenticate only to reach the narrow billing
    # recovery surface. Normal product resources remain locked.
    blocked_login = await admin_client.post(
        "/api/auth/login", json={"email": "client-admin@example.com", "password": "password123"}
    )
    assert blocked_login.status_code == 200, blocked_login.text
    assert (await admin_client.get("/api/auth/me")).status_code == 200
    assert (await admin_client.get("/api/sites")).status_code == 403
    await admin_client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "supersecret123"}
    )
    assert (await admin_client.get("/api/auth/me")).status_code == 200


async def test_org_admin_cannot_change_their_own_plan_or_limits(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    org = await _org(admin_client, "SelfServe", max_sites=1)
    headers = {"X-Acting-Org": str(org["id"])}
    await _step_up(admin_client, int(org["id"]))
    created = await admin_client.post(
        "/api/users",
        json={"email": "greedy-admin@example.com", "is_admin": True},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    await set_test_user_password(database, "greedy-admin@example.com")
    # Acting as the customer's own admin, not the operator.
    await admin_client.post(
        "/api/auth/login", json={"email": "greedy-admin@example.com", "password": "password123"}
    )
    # The whole organizations API is operator-only, so a customer cannot raise its
    # own caps, lift its suspension, or even list organizations.
    assert (await admin_client.get("/api/organizations")).status_code == 403
    raise_limit = await admin_client.patch(
        f"/api/organizations/{org['id']}", json={"max_sites": 9999}
    )
    assert raise_limit.status_code == 403
    # And the cap still bites: they cannot exceed it from the product side either.
    await admin_client.post("/api/sites", json={"url": "https://example.com/1"})
    blocked = await admin_client.post("/api/sites", json={"url": "https://example.org/2"})
    assert blocked.status_code == 403


async def test_ai_check_limit_reached(database: Database) -> None:
    async with database.session() as session:
        org_id = await create_org(session)
        org = await session.get(Organization, org_id)
        assert org is not None
        org.monthly_ai_check_limit = 2
        site = Site(url="https://x.example", organization_id=org_id)
        session.add(site)
        await session.flush()
        session.add(AIUsage(organization_id=org_id, site_id=site.id, model="gpt"))
        await session.commit()
        site_id = site.id

    async with database.session() as session:
        assert await ai_check_limit_reached(session, org_id) is False  # 1 of 2 used
        session.add_all([AIUsage(organization_id=org_id, site_id=site_id, model="gpt")])
        await session.commit()
    async with database.session() as session:
        assert await ai_check_limit_reached(session, org_id) is True  # 2 of 2 used


async def test_ai_check_limit_unlimited_when_unset(database: Database) -> None:
    async with database.session() as session:
        org_id = await create_org(session)  # monthly_ai_check_limit is NULL by default
        await session.commit()
    async with database.session() as session:
        assert await ai_check_limit_reached(session, org_id) is False
