"""Tests for edit-scope enforcement and account management."""

from __future__ import annotations

import httpx
from tests.conftest import ScriptedCapturer, set_test_user_password

from driftwatch.db import Database

_V1 = "<html><body><p>The first version of the page body</p></body></html>"
_V2 = "<html><body><p>The second version of the page body</p></body></html>"


async def _login(client: httpx.AsyncClient, email: str, password: str) -> None:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


async def _step_up(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/auth/step-up", json={"password": "password123"})
    assert response.status_code == 204, response.text


async def test_member_cannot_edit_without_a_grant(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "admin@example.com", "password": "password123"}
    )
    project_id = (await client.post("/api/projects", json={"name": "Press"})).json()["id"]
    site_id = (
        await client.post(
            "/api/sites", json={"url": "https://example.test", "project_id": project_id}
        )
    ).json()["id"]

    member_id = (
        await client.post(
            "/api/auth/register", json={"email": "member@example.com", "password": "password123"}
        )
    ).json()["id"]  # registering switches the session cookie to the member

    assert (
        await client.post("/api/sites", json={"url": "https://example.test/x"})
    ).status_code == 403
    assert (await client.patch(f"/api/sites/{site_id}", json={"name": "x"})).status_code == 403
    assert (await client.get("/api/users")).status_code == 403

    await _login(client, "admin@example.com", "password123")
    await _step_up(client)
    granted = await client.put(
        f"/api/users/{member_id}/permissions", json={"project_ids": [project_id], "site_ids": []}
    )
    assert granted.status_code == 200
    assert granted.json()["project_ids"] == [project_id]

    await _login(client, "member@example.com", "password123")
    assert (
        await client.patch(f"/api/sites/{site_id}", json={"name": "Renamed"})
    ).status_code == 200
    in_project = await client.post(
        "/api/sites", json={"url": "https://example.test/y", "project_id": project_id}
    )
    assert in_project.status_code == 201
    # A projectless site still requires admin.
    assert (
        await client.post("/api/sites", json={"url": "https://example.test/z"})
    ).status_code == 403


async def test_admin_user_management_and_self_guards(
    client: httpx.AsyncClient, database: Database
) -> None:
    admin_id = (
        await client.post(
            "/api/auth/register", json={"email": "admin@example.com", "password": "password123"}
        )
    ).json()["id"]

    await _step_up(client)
    created = await client.post("/api/users", json={"email": "member@example.com"})
    assert created.status_code == 201
    member_id = created.json()["id"]
    assert created.json()["is_admin"] is False
    await set_test_user_password(database, "member@example.com")

    assert (
        await client.patch(f"/api/users/{admin_id}", json={"is_admin": False})
    ).status_code == 404
    assert (await client.delete(f"/api/users/{admin_id}")).status_code == 404

    assert (
        await client.patch(f"/api/users/{member_id}", json={"is_active": False})
    ).status_code == 200
    await client.post("/api/auth/logout")
    blocked = await client.post(
        "/api/auth/login", json={"email": "member@example.com", "password": "password123"}
    )
    assert blocked.status_code == 403


async def test_change_retry_and_analyze_require_site_edit(
    client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    capturer.queue.extend([_V1, _V2])
    await client.post(
        "/api/auth/register", json={"email": "admin@example.com", "password": "password123"}
    )
    site_id = (await client.post("/api/sites", json={"url": "https://example.test"})).json()["id"]
    await client.post(f"/api/sites/{site_id}/check")  # baseline
    await client.post(f"/api/sites/{site_id}/check")  # detects the change
    change_id = (await client.get("/api/changes", params={"site_id": site_id})).json()[0]["id"]

    # A member with no grant must not be able to re-bill the model or re-send mail.
    member_id = (
        await client.post(
            "/api/auth/register", json={"email": "member@example.com", "password": "password123"}
        )
    ).json()["id"]
    assert (await client.post(f"/api/changes/{change_id}/retry")).status_code == 403
    assert (await client.post(f"/api/changes/{change_id}/analyze")).status_code == 403

    # Granting edit access to the site unlocks both actions.
    await _login(client, "admin@example.com", "password123")
    await _step_up(client)
    await client.put(
        f"/api/users/{member_id}/permissions", json={"project_ids": [], "site_ids": [site_id]}
    )
    await _login(client, "member@example.com", "password123")
    assert (await client.post(f"/api/changes/{change_id}/retry")).status_code == 200
    assert (await client.post(f"/api/changes/{change_id}/analyze")).status_code == 200


async def test_recipient_mutations_require_edit_access(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "admin@example.com", "password": "password123"}
    )
    project_id = (await client.post("/api/projects", json={"name": "Press"})).json()["id"]
    recipient_id = (await client.post("/api/recipients", json={"email": "ops@example.com"})).json()[
        "id"
    ]

    member_id = (
        await client.post(
            "/api/auth/register", json={"email": "member@example.com", "password": "password123"}
        )
    ).json()["id"]

    # A grantless member cannot create recipients, delete them, or redirect mail.
    assert (
        await client.post("/api/recipients", json={"email": "x@example.com"})
    ).status_code == 403
    assert (await client.delete(f"/api/recipients/{recipient_id}")).status_code == 403
    assert (
        await client.post(
            f"/api/recipients/{recipient_id}/substitutions",
            json={
                "substitute_email": "attacker@example.com",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
        )
    ).status_code == 403

    # An edit grant unlocks recipient management.
    await _login(client, "admin@example.com", "password123")
    await _step_up(client)
    await client.put(
        f"/api/users/{member_id}/permissions", json={"project_ids": [project_id], "site_ids": []}
    )
    await _login(client, "member@example.com", "password123")
    assert (
        await client.post("/api/recipients", json={"email": "new@example.com"})
    ).status_code == 201


async def test_site_editor_cannot_move_site_into_unowned_project(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "admin@example.com", "password": "password123"}
    )
    project_id = (await client.post("/api/projects", json={"name": "Locked"})).json()["id"]
    site_id = (await client.post("/api/sites", json={"url": "https://example.test"})).json()["id"]
    member_id = (
        await client.post(
            "/api/auth/register", json={"email": "member@example.com", "password": "password123"}
        )
    ).json()["id"]

    await _login(client, "admin@example.com", "password123")
    await _step_up(client)
    await client.put(
        f"/api/users/{member_id}/permissions", json={"project_ids": [], "site_ids": [site_id]}
    )
    await _login(client, "member@example.com", "password123")
    # A plain edit is allowed...
    renamed = await client.patch(f"/api/sites/{site_id}", json={"name": "Renamed"})
    assert renamed.status_code == 200
    # ...but relocating it into a project they cannot edit is not.
    moved = await client.patch(f"/api/sites/{site_id}", json={"project_id": project_id})
    assert moved.status_code == 403


async def test_recipient_access_is_scoped_to_referencing_sites(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "admin@example.com", "password": "password123"}
    )
    recipient_id = (await client.post("/api/recipients", json={"email": "ops@example.com"})).json()[
        "id"
    ]
    # The recipient is wired only to site B, which the member will not be granted.
    await client.post(
        "/api/sites", json={"url": "https://b.example.test", "recipient_ids": [recipient_id]}
    )
    site_a = (await client.post("/api/sites", json={"url": "https://a.example.test"})).json()["id"]
    member_id = (
        await client.post(
            "/api/auth/register", json={"email": "member@example.com", "password": "password123"}
        )
    ).json()["id"]

    await _login(client, "admin@example.com", "password123")
    await _step_up(client)
    await client.put(
        f"/api/users/{member_id}/permissions", json={"project_ids": [], "site_ids": [site_a]}
    )
    await _login(client, "member@example.com", "password123")
    # The recipient feeds only a site the member cannot edit → no access.
    assert (await client.delete(f"/api/recipients/{recipient_id}")).status_code == 403
    redirect = await client.post(
        f"/api/recipients/{recipient_id}/substitutions",
        json={
            "substitute_email": "attacker@example.com",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
    )
    assert redirect.status_code == 403

    await _login(client, "admin@example.com", "password123")
    assert (await client.delete(f"/api/recipients/{recipient_id}")).status_code == 204


async def test_picker_session_is_owner_scoped(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "admin@example.com", "password": "password123"}
    )
    started = await client.post(
        "/api/picker/sessions", json={"url": "https://example.test", "mode": "select"}
    )
    assert started.status_code == 201
    session_id = started.json()["session_id"]
    assert (await client.get(f"/api/picker/sessions/{session_id}")).status_code == 200

    # A different signed-in member must not see or touch the owner's session.
    await client.post(
        "/api/auth/register", json={"email": "member@example.com", "password": "password123"}
    )
    assert (await client.get(f"/api/picker/sessions/{session_id}")).status_code == 404


async def test_project_create_and_delete_are_admin_only(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "admin@example.com", "password": "password123"}
    )
    project_id = (await client.post("/api/projects", json={"name": "Owned"})).json()["id"]

    await client.post(
        "/api/auth/register", json={"email": "member@example.com", "password": "password123"}
    )
    assert (await client.post("/api/projects", json={"name": "Nope"})).status_code == 403
    assert (await client.delete(f"/api/projects/{project_id}")).status_code == 403
