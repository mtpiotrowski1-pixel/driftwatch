"""Operator accounts stay outside tenant-admin account management."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from tests.conftest import set_test_user_password

from driftwatch.db import Database
from driftwatch.models import User
from driftwatch.security.passwords import hash_password

_OPERATOR_EMAIL = "admin@example.com"
_OPERATOR_PASSWORD = "supersecret123"
_ORG_ADMIN_EMAIL = "org-admin@example.com"
_ORG_ADMIN_PASSWORD = "password123"


@dataclass(frozen=True)
class SameOrgAdmin:
    client: httpx.AsyncClient
    operator_id: int


async def _login(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await client.post("/api/auth/login", json={"email": email, "password": password})


@pytest_asyncio.fixture
async def same_org_admin(
    admin_client: httpx.AsyncClient, database: Database
) -> AsyncIterator[SameOrgAdmin]:
    operator = (await admin_client.get("/api/auth/me")).json()
    step_up = await admin_client.post("/api/auth/step-up", json={"password": _OPERATOR_PASSWORD})
    assert step_up.status_code == 204, step_up.text
    created = await admin_client.post(
        "/api/users",
        json={
            "email": _ORG_ADMIN_EMAIL,
            "is_admin": True,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["organization_id"] == operator["organization_id"]
    await set_test_user_password(database, _ORG_ADMIN_EMAIL, _ORG_ADMIN_PASSWORD)

    logged_in = await _login(admin_client, _ORG_ADMIN_EMAIL, _ORG_ADMIN_PASSWORD)
    assert logged_in.status_code == 200, logged_in.text
    yield SameOrgAdmin(admin_client, int(operator["id"]))


async def _assert_operator_still_owns_account(client: httpx.AsyncClient) -> None:
    logged_in = await _login(client, _OPERATOR_EMAIL, _OPERATOR_PASSWORD)
    assert logged_in.status_code == 200, logged_in.text
    assert logged_in.json()["user"]["is_superadmin"] is True


async def test_org_admin_does_not_list_same_org_superadmin(
    same_org_admin: SameOrgAdmin,
) -> None:
    response = await same_org_admin.client.get("/api/users")
    assert response.status_code == 200, response.text
    users = response.json()
    assert {user["email"] for user in users} == {_ORG_ADMIN_EMAIL}
    assert same_org_admin.operator_id not in {user["id"] for user in users}


@pytest.mark.parametrize(
    ("method", "suffix", "payload"),
    [
        (
            "PATCH",
            "",
            {"email": "captured@example.com", "is_admin": False, "is_active": False},
        ),
        ("POST", "/invite", None),
        ("PUT", "/permissions", {"project_ids": [], "site_ids": []}),
        ("DELETE", "", None),
    ],
    ids=["patch", "invitation", "permissions", "delete"],
)
async def test_org_admin_cannot_mutate_same_org_superadmin(
    same_org_admin: SameOrgAdmin,
    method: str,
    suffix: str,
    payload: dict[str, object] | None,
) -> None:
    # The invitation endpoint legitimately requires step-up. Satisfying it proves
    # that re-authentication alone never authorizes an operator-account takeover.
    step_up = await same_org_admin.client.post(
        "/api/auth/step-up", json={"password": _ORG_ADMIN_PASSWORD}
    )
    assert step_up.status_code == 204, step_up.text

    response = await same_org_admin.client.request(
        method,
        f"/api/users/{same_org_admin.operator_id}{suffix}",
        json=payload,
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == f"User {same_org_admin.operator_id} not found"
    await _assert_operator_still_owns_account(same_org_admin.client)


async def _seed_second_superadmin(database: Database, organization_id: int) -> int:
    async with database.session() as session:
        operator = User(
            email="second-operator@example.com",
            name="Second operator",
            password_hash=hash_password("second-password"),
            organization_id=organization_id,
            is_admin=True,
            is_superadmin=True,
        )
        session.add(operator)
        await session.commit()
        return operator.id


@pytest.mark.parametrize(
    ("method", "suffix", "payload"),
    [
        ("PATCH", "", {"name": "Recovery"}),
        ("POST", "/invite", None),
        ("PUT", "/permissions", {"project_ids": [], "site_ids": []}),
        ("DELETE", "", None),
    ],
    ids=["patch", "invitation", "permissions", "delete"],
)
async def test_superadmin_cannot_manage_operator_through_tenant_user_api(
    admin_client: httpx.AsyncClient,
    database: Database,
    method: str,
    suffix: str,
    payload: dict[str, object] | None,
) -> None:
    current = (await admin_client.get("/api/auth/me")).json()
    second_id = await _seed_second_superadmin(database, int(current["organization_id"]))

    step_up = await admin_client.post("/api/auth/step-up", json={"password": _OPERATOR_PASSWORD})
    assert step_up.status_code == 204, step_up.text
    response = await admin_client.request(
        method,
        f"/api/users/{second_id}{suffix}",
        json=payload,
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == f"User {second_id} not found"
