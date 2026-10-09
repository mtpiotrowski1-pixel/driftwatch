"""The operator's X-Acting-Org context: it scopes a superadmin's reads and
writes to an entered organization, and it is ignored for everyone else."""

from __future__ import annotations

import httpx
import pytest
from tests.conftest import set_test_user_password

from driftwatch.db import Database

_SUPERADMIN = ("admin@example.com", "supersecret123")


async def _login(client: httpx.AsyncClient, email: str, password: str) -> None:
    assert (
        await client.post("/api/auth/login", json={"email": email, "password": password})
    ).status_code == 200


async def _org(client: httpx.AsyncClient, name: str) -> int:
    step_up = await client.post("/api/auth/step-up", json={"password": _SUPERADMIN[1]})
    assert step_up.status_code == 204, step_up.text
    response = await client.post("/api/organizations", json={"name": name})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _names(response: httpx.Response) -> list[str]:
    return [project["name"] for project in response.json()]


async def test_operator_creates_and_reads_within_entered_org(
    admin_client: httpx.AsyncClient,
) -> None:
    acme = await _org(admin_client, "Acme")
    other = await _org(admin_client, "Other")

    created = await admin_client.post(
        "/api/projects", json={"name": "Acme Project"}, headers={"X-Acting-Org": str(acme)}
    )
    assert created.status_code == 201, created.text

    # Entered Acme sees it; entered Other does not; the instance view sees all.
    assert "Acme Project" in _names(
        await admin_client.get("/api/projects", headers={"X-Acting-Org": str(acme)})
    )
    assert "Acme Project" not in _names(
        await admin_client.get("/api/projects", headers={"X-Acting-Org": str(other)})
    )
    assert "Acme Project" in _names(await admin_client.get("/api/projects"))


async def test_org_admin_cannot_use_the_acting_org_header(
    admin_client: httpx.AsyncClient, database: Database
) -> None:
    acme = await _org(admin_client, "Acme")
    other = await _org(admin_client, "Other")
    await admin_client.post(
        "/api/projects", json={"name": "Other Secret"}, headers={"X-Acting-Org": str(other)}
    )
    step_up = await admin_client.post(
        "/api/auth/step-up",
        json={"password": "supersecret123"},
        headers={"X-Acting-Org": str(acme)},
    )
    assert step_up.status_code == 204, step_up.text
    created = await admin_client.post(
        "/api/users",
        json={"email": "acme-admin@example.com", "is_admin": True},
        headers={"X-Acting-Org": str(acme)},
    )
    assert created.status_code == 201, created.text
    await set_test_user_password(database, "acme-admin@example.com")

    await _login(admin_client, "acme-admin@example.com", "password123")
    # The header must be ignored for an org-admin: no peeking into another org...
    peek = await admin_client.get("/api/projects", headers={"X-Acting-Org": str(other)})
    assert "Other Secret" not in _names(peek)
    # ...and a create with the header still lands in their own org.
    await admin_client.post(
        "/api/projects", json={"name": "Acme Owned"}, headers={"X-Acting-Org": str(other)}
    )

    await _login(admin_client, *_SUPERADMIN)
    assert "Acme Owned" not in _names(
        await admin_client.get("/api/projects", headers={"X-Acting-Org": str(other)})
    )


async def test_unknown_acting_org_is_rejected_instead_of_widening_scope(
    admin_client: httpx.AsyncClient,
) -> None:
    await admin_client.post("/api/projects", json={"name": "Default Project"})
    resp = await admin_client.get("/api/projects", headers={"X-Acting-Org": "999999"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Acting organization not found"


@pytest.mark.parametrize("value", ["not-a-number", "0", "-1"])
async def test_malformed_acting_org_is_rejected(
    admin_client: httpx.AsyncClient, value: str
) -> None:
    resp = await admin_client.get("/api/projects", headers={"X-Acting-Org": value})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid acting organization"


async def test_me_reports_the_server_validated_acting_organization(
    admin_client: httpx.AsyncClient,
) -> None:
    org_id = await _org(admin_client, "Confirmed context")

    entered = await admin_client.get("/api/auth/me", headers={"X-Acting-Org": str(org_id)})
    assert entered.status_code == 200, entered.text
    assert entered.json()["acting_organization_id"] == org_id
    assert entered.json()["acting_organization_name"] == "Confirmed context"

    instance = await admin_client.get("/api/auth/me")
    assert instance.status_code == 200, instance.text
    assert instance.json()["acting_organization_id"] is None
    assert instance.json()["acting_organization_name"] is None


@pytest.mark.parametrize(
    "path",
    [
        "/api/organizations",
        "/api/plans",
        "/api/plans/pricing",
        "/api/plans/suggest",
        "/api/billing/prices",
        "/api/admin/capabilities",
        "/api/operations/overview",
        "/api/operators",
    ],
)
async def test_instance_control_plane_rejects_an_acting_organization(
    admin_client: httpx.AsyncClient,
    path: str,
) -> None:
    org_id = await _org(admin_client, "Scoped support customer")

    response = await admin_client.get(path, headers={"X-Acting-Org": str(org_id)})

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == (
        "Exit the active organization before managing instance resources"
    )


async def test_instance_mutation_cannot_run_inside_an_acting_organization(
    admin_client: httpx.AsyncClient,
) -> None:
    org_id = await _org(admin_client, "Support boundary")

    response = await admin_client.post(
        "/api/organizations",
        json={"name": "Must not be created"},
        headers={"X-Acting-Org": str(org_id)},
    )

    assert response.status_code == 409, response.text
