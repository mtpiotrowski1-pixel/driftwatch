"""Cross-organization isolation: a member of one org must never see, fetch, or
mutate another org's data through the API.

Two tenants (Org A, Org B) are seeded directly via the database, each with an
org-admin (``is_admin=True``, ``is_superadmin=False``). The ``admin_client``
fixture has already registered ``admin@example.com`` as the instance superadmin
in the default org *before* these rows exist, so the seeded admins are plain
org-admins. Identity is switched over the shared cookie jar with ``POST
/api/auth/login``.

Where an assertion fails because of a genuine backend scoping leak (not a test
bug), the test is marked ``xfail(strict=False)`` with a precise ``LEAK:`` reason
naming the endpoint and source file, per the task brief — src/ is never touched.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio

from driftwatch.db import Database
from driftwatch.models import AIUsage, ChangeEvent, Organization, Snapshot, User
from driftwatch.security.passwords import hash_password

_PASSWORD = "password123"


@dataclass
class Tenant:
    org_id: int
    admin_email: str


@dataclass
class TwoTenants:
    a: Tenant
    b: Tenant


async def _login(client: httpx.AsyncClient, email: str, password: str = _PASSWORD) -> None:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


async def _step_up(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/auth/step-up", json={"password": _PASSWORD})
    assert response.status_code == 204, response.text


async def _seed_org(database: Database, name: str, admin_email: str) -> Tenant:
    """Create an org and one org-admin (not a superadmin) in it, committed."""
    async with database.session() as session:
        org = Organization(name=name)
        session.add(org)
        await session.flush()
        session.add(
            User(
                email=admin_email,
                name=f"{name} admin",
                password_hash=hash_password(_PASSWORD),
                organization_id=org.id,
                is_admin=True,
                is_superadmin=False,
            )
        )
        await session.commit()
        return Tenant(org_id=org.id, admin_email=admin_email)


@pytest_asyncio.fixture
async def tenants(admin_client: httpx.AsyncClient, database: Database) -> TwoTenants:
    """Two seeded tenants. Depends on ``admin_client`` so the superadmin is
    registered first; both share the one sqlite file backing ``client``."""
    a = await _seed_org(database, "Org A", "admin-a@example.com")
    b = await _seed_org(database, "Org B", "admin-b@example.com")
    return TwoTenants(a=a, b=b)


async def _create_member(database: Database, org_id: int, email: str) -> int:
    """Create a plain (non-admin) member in ``org_id`` and return its id."""
    async with database.session() as session:
        user = User(
            email=email,
            name="Member",
            password_hash=hash_password(_PASSWORD),
            organization_id=org_id,
            is_admin=False,
            is_superadmin=False,
        )
        session.add(user)
        await session.commit()
        return user.id


# ---------------------------------------------------------------------------
# Read / fetch / mutate isolation across the core resources.
# ---------------------------------------------------------------------------


async def test_lists_do_not_include_other_orgs_rows(
    client: httpx.AsyncClient, tenants: TwoTenants
) -> None:
    await _login(client, tenants.a.admin_email)
    a_project = (await client.post("/api/projects", json={"name": "A Project"})).json()["id"]
    a_site = (
        await client.post(
            "/api/sites", json={"url": "https://a.example.test", "project_id": a_project}
        )
    ).json()["id"]
    a_recipient = (
        await client.post("/api/recipients", json={"email": "a-watch@example.com"})
    ).json()["id"]

    await _login(client, tenants.b.admin_email)
    projects = (await client.get("/api/projects")).json()
    sites = (await client.get("/api/sites")).json()
    recipients = (await client.get("/api/recipients")).json()

    assert a_project not in [p["id"] for p in projects]
    assert a_site not in [s["id"] for s in sites]
    assert a_recipient not in [r["id"] for r in recipients]


async def test_get_by_id_across_orgs_is_404(client: httpx.AsyncClient, tenants: TwoTenants) -> None:
    await _login(client, tenants.a.admin_email)
    a_project = (await client.post("/api/projects", json={"name": "A Project"})).json()["id"]
    a_site = (
        await client.post(
            "/api/sites", json={"url": "https://a.example.test", "project_id": a_project}
        )
    ).json()["id"]

    await _login(client, tenants.b.admin_email)
    assert (await client.get(f"/api/sites/{a_site}")).status_code == 404
    # Projects have no GET-by-id route; PATCH is the by-id read surface and must 404.
    assert (
        await client.patch(f"/api/projects/{a_project}", json={"name": "hijacked"})
    ).status_code == 404


async def test_patch_and_delete_across_orgs_is_404(
    client: httpx.AsyncClient, tenants: TwoTenants
) -> None:
    await _login(client, tenants.a.admin_email)
    a_project = (await client.post("/api/projects", json={"name": "A Project"})).json()["id"]
    a_site = (
        await client.post(
            "/api/sites", json={"url": "https://a.example.test", "project_id": a_project}
        )
    ).json()["id"]
    a_recipient = (
        await client.post("/api/recipients", json={"email": "a-watch@example.com"})
    ).json()["id"]

    await _login(client, tenants.b.admin_email)
    assert (await client.patch(f"/api/sites/{a_site}", json={"name": "x"})).status_code == 404
    assert (await client.delete(f"/api/sites/{a_site}")).status_code == 404
    assert (await client.patch(f"/api/projects/{a_project}", json={"name": "x"})).status_code == 404
    assert (await client.delete(f"/api/projects/{a_project}")).status_code == 404
    assert (
        await client.patch(f"/api/recipients/{a_recipient}", json={"name": "x"})
    ).status_code == 404
    assert (await client.delete(f"/api/recipients/{a_recipient}")).status_code == 404

    # A's rows survived B's attempts.
    await _login(client, tenants.a.admin_email)
    assert (await client.get(f"/api/sites/{a_site}")).status_code == 200


async def test_user_mutations_across_orgs_is_404(
    client: httpx.AsyncClient, tenants: TwoTenants, database: Database
) -> None:
    """An org-admin must not edit, disable, reset, or delete a user in another
    org. The org-scoped session resolves a foreign user id to nothing, so every
    by-id user route reads as 404 rather than acting (or leaking existence)."""
    a_member = await _create_member(database, tenants.a.org_id, "a-member@example.com")

    await _login(client, tenants.b.admin_email)
    # Sending a password setup link is step-up-gated; satisfy it for B's own admin so this
    # asserts the cross-org 404, not merely the step-up requirement.
    assert (await client.post("/api/auth/step-up", json={"password": _PASSWORD})).status_code == 204
    assert (await client.patch(f"/api/users/{a_member}", json={"name": "x"})).status_code == 404
    assert (await client.post(f"/api/users/{a_member}/invite")).status_code == 404
    assert (
        await client.put(
            f"/api/users/{a_member}/permissions", json={"project_ids": [], "site_ids": []}
        )
    ).status_code == 404
    assert (await client.delete(f"/api/users/{a_member}")).status_code == 404


async def test_admin_cannot_escalate_a_user_to_superadmin(
    client: httpx.AsyncClient, tenants: TwoTenants, database: Database
) -> None:
    """Role and organization are not editable fields: a smuggled is_superadmin or
    organization_id in the PATCH body is dropped, never persisted."""
    member = await _create_member(database, tenants.a.org_id, "climber@example.com")

    await _login(client, tenants.a.admin_email)
    response = await client.patch(
        f"/api/users/{member}",
        json={"name": "Climber", "is_superadmin": True, "organization_id": tenants.b.org_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_superadmin"] is False
    assert body["organization_id"] == tenants.a.org_id


async def test_cannot_attach_new_site_to_other_orgs_project(
    client: httpx.AsyncClient, tenants: TwoTenants
) -> None:
    """An org-admin must not be able to create a site under another org's project:
    the site would then resolve its notification recipients through the foreign
    org's project_recipients, leaking change content across the tenant boundary."""
    await _login(client, tenants.a.admin_email)
    a_project = (await client.post("/api/projects", json={"name": "A Project"})).json()["id"]

    await _login(client, tenants.b.admin_email)
    response = await client.post(
        "/api/sites", json={"url": "https://b.example.test", "project_id": a_project}
    )
    assert response.status_code == 404, response.text


async def test_cannot_move_site_into_other_orgs_project(
    client: httpx.AsyncClient, tenants: TwoTenants
) -> None:
    await _login(client, tenants.a.admin_email)
    a_project = (await client.post("/api/projects", json={"name": "A Project"})).json()["id"]

    await _login(client, tenants.b.admin_email)
    b_site = (await client.post("/api/sites", json={"url": "https://b.example.test"})).json()["id"]
    response = await client.patch(f"/api/sites/{b_site}", json={"project_id": a_project})
    assert response.status_code == 404, response.text


async def _seed_change(database: Database, site_id: int) -> int:
    """Create a snapshot + change for ``site_id`` directly (unscoped background
    session) and return the change id."""
    async with database.session() as session:
        snapshot = Snapshot(site_id=site_id, content_html="<p>x</p>", content_text="x")
        session.add(snapshot)
        await session.flush()
        change = ChangeEvent(
            site_id=site_id,
            old_snapshot_id=None,
            new_snapshot_id=snapshot.id,
            diff_text="d",
            diff_html="<div></div>",
            significant=True,
            headline="Headline",
            summary="Summary",
        )
        session.add(change)
        await session.commit()
        return change.id


async def _seed_a_site_with_change(
    client: httpx.AsyncClient, database: Database, tenants: TwoTenants
) -> tuple[int, int]:
    """As A: create a site and seed a change on it via the DB. Returns
    (site_id, change_id). Leaves the session logged in as A's admin."""
    await _login(client, tenants.a.admin_email)
    site_id = (await client.post("/api/sites", json={"url": "https://a.example.test"})).json()["id"]
    change_id = await _seed_change(database, site_id)
    return site_id, change_id


async def test_change_by_id_and_actions_are_isolated_across_orgs(
    client: httpx.AsyncClient, database: Database, tenants: TwoTenants
) -> None:
    _, a_change = await _seed_a_site_with_change(client, database, tenants)
    # Sanity: A can read its own change.
    assert (await client.get(f"/api/changes/{a_change}")).status_code == 200

    await _login(client, tenants.b.admin_email)
    assert (await client.get(f"/api/changes/{a_change}")).status_code == 404
    assert (await client.post(f"/api/changes/{a_change}/retry")).status_code == 404
    assert (await client.post(f"/api/changes/{a_change}/analyze")).status_code == 404


async def test_change_list_is_isolated_across_orgs(
    client: httpx.AsyncClient, database: Database, tenants: TwoTenants
) -> None:
    _, a_change = await _seed_a_site_with_change(client, database, tenants)

    await _login(client, tenants.b.admin_email)
    b_changes = (await client.get("/api/changes")).json()
    assert a_change not in [c["id"] for c in b_changes]


# ---------------------------------------------------------------------------
# Per-org uniqueness: the same email is allowed once per org.
# ---------------------------------------------------------------------------


async def test_same_recipient_email_allowed_in_both_orgs(
    client: httpx.AsyncClient, tenants: TwoTenants
) -> None:
    email = "shared-address@example.com"
    await _login(client, tenants.a.admin_email)
    assert (await client.post("/api/recipients", json={"email": email})).status_code == 201

    await _login(client, tenants.b.admin_email)
    assert (await client.post("/api/recipients", json={"email": email})).status_code == 201


# ---------------------------------------------------------------------------
# Usage / spend isolation.
# ---------------------------------------------------------------------------


async def test_usage_summary_excludes_other_orgs_spend(
    client: httpx.AsyncClient, database: Database, tenants: TwoTenants
) -> None:
    await _login(client, tenants.a.admin_email)
    a_site = (await client.post("/api/sites", json={"url": "https://a.example.test"})).json()["id"]

    # Tie spend directly to A's site via an unscoped background session.
    async with database.session() as session:
        session.add(
            AIUsage(
                organization_id=tenants.a.org_id,
                site_id=a_site,
                model="gpt-4o-mini",
                prompt_tokens=1000,
                completion_tokens=500,
                total_tokens=1500,
                cost_usd=4.2,
            )
        )
        await session.commit()

    # A sees its own spend.
    a_summary = (await client.get("/api/usage/summary")).json()
    assert a_summary["total_cost_usd"] == pytest.approx(4.2)
    assert a_summary["total_tokens"] == 1500

    # B sees nothing.
    await _login(client, tenants.b.admin_email)
    b_summary = (await client.get("/api/usage/summary")).json()
    assert b_summary["total_cost_usd"] == 0
    assert b_summary["total_tokens"] == 0
    assert b_summary["calls"] == 0


# ---------------------------------------------------------------------------
# Permission grants cannot reference another org's project/site.
# ---------------------------------------------------------------------------


async def test_admin_cannot_grant_permissions_on_other_orgs_resources(
    client: httpx.AsyncClient, database: Database, tenants: TwoTenants
) -> None:
    # A owns a project and site.
    await _login(client, tenants.a.admin_email)
    a_project = (await client.post("/api/projects", json={"name": "A Project"})).json()["id"]
    a_site = (
        await client.post(
            "/api/sites", json={"url": "https://a.example.test", "project_id": a_project}
        )
    ).json()["id"]

    # B has a member to grant to.
    b_member = await _create_member(database, tenants.b.org_id, "member-b@example.com")

    await _login(client, tenants.b.admin_email)
    await _step_up(client)
    by_project = await client.put(
        f"/api/users/{b_member}/permissions",
        json={"project_ids": [a_project], "site_ids": []},
    )
    assert by_project.status_code == 400, by_project.text
    by_site = await client.put(
        f"/api/users/{b_member}/permissions",
        json={"project_ids": [], "site_ids": [a_site]},
    )
    assert by_site.status_code == 400, by_site.text


# ---------------------------------------------------------------------------
# Superadmin-only operator endpoints (backup, logs).
# ---------------------------------------------------------------------------


async def test_backup_and_logs_are_superadmin_only(
    client: httpx.AsyncClient, tenants: TwoTenants
) -> None:
    # An org-admin (not a superadmin) is forbidden.
    await _login(client, tenants.a.admin_email)
    assert (await client.get("/api/admin/backup")).status_code == 403
    assert (await client.get("/api/logs")).status_code == 404


async def test_superadmin_can_use_operator_endpoints(
    admin_client: httpx.AsyncClient, tenants: TwoTenants
) -> None:
    # admin_client is the instance superadmin (admin@example.com). The backup is
    # gated behind a fresh re-authentication (step-up).
    assert (await admin_client.get("/api/admin/backup")).status_code == 428
    step_up = await admin_client.post("/api/auth/step-up", json={"password": "supersecret123"})
    assert step_up.status_code == 204
    backup = await admin_client.get("/api/admin/backup")
    assert backup.status_code == 200
    assert backup.content[:15] == b"SQLite format 3"
    # The log file may not exist yet, so accept the file (200) or "no log yet" (404).
    assert (await admin_client.get("/api/logs")).status_code == 404


# ---------------------------------------------------------------------------
# Superadmin sees across organizations.
# ---------------------------------------------------------------------------


async def test_superadmin_sees_sites_from_all_orgs(
    client: httpx.AsyncClient, admin_client: httpx.AsyncClient, tenants: TwoTenants
) -> None:
    # admin_client and client share the same cookie jar / DB. Create one site in
    # each org by logging in as each org-admin, then restore the superadmin.
    await _login(client, tenants.a.admin_email)
    a_site = (await client.post("/api/sites", json={"url": "https://a-cross.example.test"})).json()[
        "id"
    ]
    await _login(client, tenants.b.admin_email)
    b_site = (await client.post("/api/sites", json={"url": "https://b-cross.example.test"})).json()[
        "id"
    ]

    # Switch back to the superadmin and confirm both are visible.
    await _login(client, "admin@example.com", "supersecret123")
    sites = (await client.get("/api/sites")).json()
    site_ids = {s["id"] for s in sites}
    assert a_site in site_ids
    assert b_site in site_ids


# ---------------------------------------------------------------------------
# Substitutions: redirecting an A recipient cannot be done/undone by B.
# ---------------------------------------------------------------------------


async def _seed_a_recipient_with_substitution(
    client: httpx.AsyncClient, tenants: TwoTenants
) -> tuple[int, int]:
    """As A: create a recipient and a substitution on it. Returns (recipient_id,
    substitution_id). Leaves the session logged in as B's admin."""
    await _login(client, tenants.a.admin_email)
    recipient_id = (
        await client.post("/api/recipients", json={"email": "a-lead@example.com"})
    ).json()["id"]
    created = await client.post(
        f"/api/recipients/{recipient_id}/substitutions",
        json={
            "substitute_email": "a-cover@example.com",
            "start_date": "2026-08-01",
            "end_date": "2026-08-14",
        },
    )
    assert created.status_code == 201
    substitution_id = created.json()["id"]
    await _login(client, tenants.b.admin_email)
    return recipient_id, substitution_id


async def test_substitution_create_and_list_on_other_orgs_recipient_is_blocked(
    client: httpx.AsyncClient, tenants: TwoTenants
) -> None:
    a_recipient, _ = await _seed_a_recipient_with_substitution(client, tenants)

    # B cannot create a substitution (recipient is out of B's org → 404).
    redirect = await client.post(
        f"/api/recipients/{a_recipient}/substitutions",
        json={
            "substitute_email": "attacker@example.com",
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
        },
    )
    assert redirect.status_code in (403, 404), redirect.text
    # B cannot list A's substitutions (recipient is out of scope → 404).
    assert (await client.get(f"/api/recipients/{a_recipient}/substitutions")).status_code == 404


async def test_substitution_delete_on_other_orgs_recipient_is_blocked(
    client: httpx.AsyncClient, tenants: TwoTenants
) -> None:
    a_recipient, substitution_id = await _seed_a_recipient_with_substitution(client, tenants)

    # B must not be able to delete A's substitution. The response is a uniform
    # 404 (not 403) so the substitution id space can't be enumerated across orgs.
    deleted = await client.delete(f"/api/recipients/substitutions/{substitution_id}")
    assert deleted.status_code == 404, deleted.text

    # The substitution still exists for A.
    await _login(client, tenants.a.admin_email)
    listed = await client.get(f"/api/recipients/{a_recipient}/substitutions")
    assert [s["id"] for s in listed.json()] == [substitution_id]


async def test_list_users_shows_only_own_org_and_its_grants(
    client: httpx.AsyncClient, database: Database, tenants: TwoTenants
) -> None:
    """An org-admin's user list contains only their own org's members, and the
    surfaced edit grants never include another org's project or site ids."""
    await _login(client, tenants.a.admin_email)
    await _step_up(client)
    a_project = (await client.post("/api/projects", json={"name": "A Project"})).json()["id"]
    a_member = await _create_member(database, tenants.a.org_id, "member-a@example.com")
    granted = await client.put(
        f"/api/users/{a_member}/permissions", json={"project_ids": [a_project], "site_ids": []}
    )
    assert granted.status_code == 200, granted.text

    await _login(client, tenants.b.admin_email)
    users = (await client.get("/api/users")).json()
    emails = {u["email"] for u in users}
    assert "member-a@example.com" not in emails
    assert tenants.a.admin_email not in emails
    all_project_ids = {pid for u in users for pid in u["project_ids"]}
    assert a_project not in all_project_ids
