"""The subscription-plan catalog: operator-only CRUD, the pricing endpoints, and
assigning a plan onto an organization."""

from __future__ import annotations

from typing import Any

import httpx
import pytest_asyncio
from tests.conftest import set_test_user_password

from driftwatch.db import Database
from driftwatch.models import BillingPrice, Plan


async def _step_up(client: httpx.AsyncClient, organization_id: int | None = None) -> None:
    headers = {"X-Acting-Org": str(organization_id)} if organization_id is not None else None
    response = await client.post(
        "/api/auth/step-up",
        headers=headers,
        json={"password": "supersecret123"},
    )
    assert response.status_code == 204, response.text


@pytest_asyncio.fixture(autouse=True)
async def _fresh_operator_proof(admin_client: httpx.AsyncClient) -> None:
    """Catalog scenarios start after the operator confirms a privileged action."""
    await _step_up(admin_client)


def _plan_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "key": "starter",
        "name": "Starter",
        "max_sites": 5,
        "max_members": 3,
        "monthly_ai_check_limit": 500,
        "currency": "USD",
    }
    body.update(overrides)
    return body


async def _login_as_client_admin(
    admin_client: httpx.AsyncClient, database: Database, org_id: int
) -> None:
    """Create an org-admin inside ``org_id`` and switch the session to them."""
    await _step_up(admin_client, org_id)
    created = await admin_client.post(
        "/api/users",
        json={"email": "client@example.com", "is_admin": True},
        headers={"X-Acting-Org": str(org_id)},
    )
    assert created.status_code == 201, created.text
    await set_test_user_password(database, "client@example.com")
    logged_in = await admin_client.post(
        "/api/auth/login", json={"email": "client@example.com", "password": "password123"}
    )
    assert logged_in.status_code == 200, logged_in.text


async def test_operator_can_crud_plans(admin_client: httpx.AsyncClient) -> None:
    created = await admin_client.post("/api/plans", json=_plan_body())
    assert created.status_code == 201, created.text
    plan = created.json()
    assert plan["key"] == "starter"
    assert plan["max_members"] == 3
    # With no override, the price follows the algorithm.
    assert plan["price_override_cents"] is None
    assert plan["effective_price_cents"] == plan["suggested_price_cents"]

    listed = await admin_client.get("/api/plans")
    assert [p["key"] for p in listed.json()] == ["starter"]

    patched = (
        await admin_client.patch(f"/api/plans/{plan['id']}", json={"price_override_cents": 2500})
    ).json()
    assert patched["price_override_cents"] == 2500
    assert patched["effective_price_cents"] == 2500

    assert (await admin_client.delete(f"/api/plans/{plan['id']}")).status_code == 204
    assert (await admin_client.get("/api/plans")).json() == []


async def test_clearing_the_override_returns_to_the_algorithm_price(
    admin_client: httpx.AsyncClient,
) -> None:
    plan = (
        await admin_client.post("/api/plans", json=_plan_body(price_override_cents=12345))
    ).json()
    assert plan["effective_price_cents"] == 12345

    cleared = (
        await admin_client.patch(f"/api/plans/{plan['id']}", json={"price_override_cents": None})
    ).json()
    assert cleared["price_override_cents"] is None
    assert cleared["effective_price_cents"] == cleared["suggested_price_cents"]


async def test_duplicate_key_is_rejected(admin_client: httpx.AsyncClient) -> None:
    assert (await admin_client.post("/api/plans", json=_plan_body())).status_code == 201
    duplicate = await admin_client.post("/api/plans", json=_plan_body(name="Another"))
    assert duplicate.status_code == 409


async def test_self_serve_flag_cannot_be_enabled_by_operator(
    admin_client: httpx.AsyncClient,
) -> None:
    detail = "Self-serve plans are disabled until verified payment activation is available"
    create = await admin_client.post(
        "/api/plans",
        json=_plan_body(key="pro", name="Pro", price_override_cents=4900, is_self_serve=True),
    )
    assert create.status_code == 409
    assert create.json()["detail"] == detail

    plan = (await admin_client.post("/api/plans", json=_plan_body())).json()
    update = await admin_client.patch(f"/api/plans/{plan['id']}", json={"is_self_serve": True})
    assert update.status_code == 409
    assert update.json()["detail"] == detail
    persisted = (await admin_client.get("/api/plans")).json()[0]
    assert persisted["is_self_serve"] is False


async def test_public_catalog_is_unauthenticated_and_empty_with_legacy_self_serve_plan(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    async with database.session() as session:
        session.add(
            Plan(
                key="legacy-public",
                name="Legacy public",
                max_sites=None,
                monthly_ai_check_limit=None,
                price_override_cents=4900,
                is_self_serve=True,
            )
        )
        await session.commit()

    admin_client.cookies.clear()  # drop the operator session entirely
    public = await admin_client.get("/api/plans/public")
    assert public.status_code == 200
    assert public.json() == []

    # The full catalogue still needs the operator session.
    assert (await admin_client.get("/api/plans")).status_code == 401


async def test_the_catalog_is_operator_only(
    admin_client: httpx.AsyncClient, database: Database
) -> None:
    org = (await admin_client.post("/api/organizations", json={"name": "Acme"})).json()
    await _step_up(admin_client)
    await _login_as_client_admin(admin_client, database, org["id"])
    assert (await admin_client.get("/api/plans")).status_code == 403
    assert (await admin_client.post("/api/plans", json=_plan_body())).status_code == 403
    assert (await admin_client.get("/api/plans/pricing")).status_code == 403


async def test_assigning_a_plan_copies_its_caps_onto_the_org(
    admin_client: httpx.AsyncClient,
) -> None:
    plan = (
        await admin_client.post(
            "/api/plans",
            json=_plan_body(max_sites=7, max_members=9, monthly_ai_check_limit=900),
        )
    ).json()
    org = (await admin_client.post("/api/organizations", json={"name": "Acme"})).json()
    await _step_up(admin_client)
    updated = (
        await admin_client.patch(f"/api/organizations/{org['id']}", json={"plan_id": plan["id"]})
    ).json()
    assert updated["plan_id"] == plan["id"]
    assert updated["plan"] == "starter"
    assert updated["max_sites"] == 7
    assert updated["max_members"] == 9
    assert updated["monthly_ai_check_limit"] == 900


async def test_an_explicit_cap_overrides_the_plan_in_the_same_request(
    admin_client: httpx.AsyncClient,
) -> None:
    plan = (
        await admin_client.post(
            "/api/plans", json=_plan_body(max_sites=50, monthly_ai_check_limit=2000)
        )
    ).json()
    org = (await admin_client.post("/api/organizations", json={"name": "Acme"})).json()
    await _step_up(admin_client)
    updated = (
        await admin_client.patch(
            f"/api/organizations/{org['id']}",
            json={
                "plan_id": plan["id"],
                "max_sites": 1,
                "max_members": 2,
                "monthly_ai_check_limit": 1,
            },
        )
    ).json()
    # The plan is recorded, but the caps sent alongside it win over the plan's.
    assert updated["plan_id"] == plan["id"]
    assert updated["max_sites"] == 1
    assert updated["max_members"] == 2
    assert updated["monthly_ai_check_limit"] == 1


async def test_deleting_a_plan_detaches_orgs_but_keeps_their_caps(
    admin_client: httpx.AsyncClient,
) -> None:
    plan = (await admin_client.post("/api/plans", json=_plan_body(max_sites=3))).json()
    org = (await admin_client.post("/api/organizations", json={"name": "Acme"})).json()
    await _step_up(admin_client)
    await admin_client.patch(f"/api/organizations/{org['id']}", json={"plan_id": plan["id"]})

    await admin_client.delete(f"/api/plans/{plan['id']}")

    after = {o["id"]: o for o in (await admin_client.get("/api/organizations")).json()}[org["id"]]
    assert after["plan_id"] is None
    assert after["max_sites"] == 3  # the copied cap is retained


async def test_published_plan_contract_is_immutable_and_must_be_versioned(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    plan = (await admin_client.post("/api/plans", json=_plan_body())).json()
    async with database.session() as session:
        session.add(
            BillingPrice(
                plan_id=plan["id"],
                provider="stripe",
                provider_price_id="price_immutable_contract",
                version=1,
                unit_amount_minor=4900,
                currency="USD",
            )
        )
        await session.commit()

    detail = (
        "A plan with billing price history has immutable contract fields; "
        "create a new plan version instead"
    )
    for patch in (
        {"key": "starter-v2"},
        {"max_sites": 10},
        {"max_members": 10},
        {"monthly_ai_check_limit": 900},
        {"currency": "EUR"},
    ):
        response = await admin_client.patch(f"/api/plans/{plan['id']}", json=patch)
        assert response.status_code == 409
        assert response.json()["detail"] == detail

    # Archiving remains possible. The UI submits unchanged contract fields along
    # with the active flag, so identical values must not trigger the guard.
    archived = await admin_client.patch(
        f"/api/plans/{plan['id']}",
        json={
            "key": plan["key"],
            "max_sites": plan["max_sites"],
            "max_members": plan["max_members"],
            "monthly_ai_check_limit": plan["monthly_ai_check_limit"],
            "currency": plan["currency"],
            "is_active": False,
        },
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["is_active"] is False

    deleted = await admin_client.delete(f"/api/plans/{plan['id']}")
    assert deleted.status_code == 409
    assert "create a new plan version" in deleted.json()["detail"]


async def test_pricing_knobs_drive_the_suggested_price(admin_client: httpx.AsyncClient) -> None:
    params = {"max_sites": 10, "monthly_ai_check_limit": 1000}
    base = (await admin_client.get("/api/plans/suggest", params=params)).json()
    context = (await admin_client.get("/api/plans/pricing")).json()

    raised = await admin_client.put(
        "/api/plans/pricing", json={"ai_margin": context["ai_margin"] * 2 + 1}
    )
    assert raised.status_code == 200

    higher = (await admin_client.get("/api/plans/suggest", params=params)).json()
    assert higher["suggested_price_cents"] > base["suggested_price_cents"]
