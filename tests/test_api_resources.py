"""Tests for the site, project, recipient, change, settings, and export APIs."""

from __future__ import annotations

import httpx
from tests.conftest import ScriptedCapturer

_PAGE_V1 = "<html><body><h1>Docs</h1><p>The first version of the page body</p></body></html>"
_PAGE_V2 = "<html><body><h1>Docs</h1><p>The second version of the page body</p></body></html>"


async def test_site_crud_round_trip(admin_client: httpx.AsyncClient) -> None:
    created = await admin_client.post(
        "/api/sites",
        json={"url": "https://example.test", "name": "Example", "check_interval_minutes": 30},
    )
    assert created.status_code == 201
    site_id = created.json()["id"]

    listed = await admin_client.get("/api/sites")
    assert [site["id"] for site in listed.json()] == [site_id]

    patched = await admin_client.patch(f"/api/sites/{site_id}", json={"name": "Renamed"})
    assert patched.json()["name"] == "Renamed"

    assert (await admin_client.delete(f"/api/sites/{site_id}")).status_code == 204
    assert (await admin_client.get(f"/api/sites/{site_id}")).status_code == 404


async def test_site_create_validates_interval(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.post(
        "/api/sites", json={"url": "https://example.test", "check_interval_minutes": 0}
    )
    assert response.status_code == 422


async def test_site_links_recipients(admin_client: httpx.AsyncClient) -> None:
    recipient = await admin_client.post(
        "/api/recipients", json={"email": "watcher@example.com", "name": "Watcher"}
    )
    recipient_id = recipient.json()["id"]
    site = await admin_client.post(
        "/api/sites", json={"url": "https://example.test", "recipient_ids": [recipient_id]}
    )
    assert site.json()["recipient_ids"] == [recipient_id]


async def test_check_now_baseline_then_change(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    capturer.queue.extend([_PAGE_V1, _PAGE_V2])
    site = await admin_client.post("/api/sites", json={"url": "https://example.test"})
    site_id = site.json()["id"]

    baseline = await admin_client.post(f"/api/sites/{site_id}/check")
    assert baseline.json()["status"] == "baseline"

    changed = await admin_client.post(f"/api/sites/{site_id}/check")
    body = changed.json()
    assert body["status"] == "changed"
    # With no recipients and no webhook the AI analysis is skipped entirely
    # (nothing could be delivered), so there is no verdict and no notification.
    assert body["significant"] is None
    assert body["notified"] is False

    changes = await admin_client.get("/api/changes", params={"site_id": site_id})
    assert len(changes.json()) == 1
    detail = await admin_client.get(f"/api/changes/{changes.json()[0]['id']}")
    assert "second version" in detail.json()["diff_text"]


async def test_recipient_duplicate_email_conflicts(admin_client: httpx.AsyncClient) -> None:
    await admin_client.post("/api/recipients", json={"email": "dupe@example.com"})
    second = await admin_client.post("/api/recipients", json={"email": "dupe@example.com"})
    assert second.status_code == 409


async def test_project_groups_sites(admin_client: httpx.AsyncClient) -> None:
    project = await admin_client.post(
        "/api/projects", json={"name": "Press", "notification_mode": "always"}
    )
    project_id = project.json()["id"]
    await admin_client.post(
        "/api/sites", json={"url": "https://example.test", "project_id": project_id}
    )

    projects = await admin_client.get("/api/projects")
    assert projects.json()[0]["site_count"] == 1


async def test_settings_require_admin(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "admin@example.com", "password": "password123"}
    )
    await client.post(
        "/api/auth/register", json={"email": "member@example.com", "password": "password123"}
    )  # cookie now belongs to the member

    assert (await client.get("/api/settings")).status_code == 403

    await client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "password123"}
    )
    await client.post("/api/auth/step-up", json={"password": "password123"})
    updated = await client.put(
        "/api/settings", json={"openai_api_key": "sk-secret", "openai_model": "gpt-4o"}
    )
    assert updated.status_code == 200
    assert updated.json()["openai_api_key"] == "********"
    assert updated.json()["openai_model"] == "gpt-4o"


async def test_usage_summary_starts_empty(admin_client: httpx.AsyncClient) -> None:
    summary = await admin_client.get("/api/usage/summary")
    assert summary.status_code == 200
    assert summary.json()["calls"] == 0


async def test_usage_breakdown_after_a_change(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    capturer.queue.extend([_PAGE_V1, _PAGE_V2])
    recipient_id = (
        await admin_client.post("/api/recipients", json={"email": "usage@example.com"})
    ).json()["id"]
    site_id = (
        await admin_client.post(
            "/api/sites",
            json={
                "url": "https://example.test",
                "name": "Acme",
                "recipient_ids": [recipient_id],
            },
        )
    ).json()["id"]
    await admin_client.post(f"/api/sites/{site_id}/check")  # baseline
    await admin_client.post(f"/api/sites/{site_id}/check")  # change -> analysis records usage

    summary = (await admin_client.get("/api/usage/summary")).json()
    assert summary["calls"] >= 1
    assert summary["by_model"]
    assert any(bucket["label"] == "Acme" for bucket in summary["by_site"])
    assert summary["by_month"]


async def test_changes_export_returns_xlsx(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/api/exports/changes.xlsx")
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    assert response.content[:2] == b"PK"  # xlsx is a zip archive


async def test_origin_guard_rejects_cross_site_mutation(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.post(
        "/api/recipients",
        json={"email": "evil@example.com"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
