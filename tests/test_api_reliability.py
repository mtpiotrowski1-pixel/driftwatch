"""API tests for security headers, dry checks, snapshots, and the audit log."""

from __future__ import annotations

import httpx
from tests.conftest import ScriptedCapturer

_V1 = "<html><body><h1>Docs</h1><p>The first version of the page body</p></body></html>"
_V2 = "<html><body><h1>Docs</h1><p>The second version of the page body</p></body></html>"


async def test_security_headers_present(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "referrer-policy" in response.headers
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "permissions-policy" in response.headers


async def test_api_responses_are_not_cached(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/api/sites")
    assert response.headers.get("cache-control") == "no-store"


async def test_create_site_rejects_unsafe_url(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.post("/api/sites", json={"url": "http://localhost:9000/admin"})
    assert response.status_code == 400


async def test_dry_check_skips_analysis(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    capturer.queue.extend([_V1, _V2])
    site_id = (await admin_client.post("/api/sites", json={"url": "https://example.test"})).json()[
        "id"
    ]

    await admin_client.post(f"/api/sites/{site_id}/check", params={"analyze": "false"})
    changed = await admin_client.post(f"/api/sites/{site_id}/check", params={"analyze": "false"})
    assert changed.json()["status"] == "changed"

    changes = (await admin_client.get("/api/changes", params={"site_id": site_id})).json()
    assert len(changes) == 1
    assert changes[0]["significant"] is None  # analysis was skipped


async def test_snapshot_rebaselines(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    capturer.queue.extend([_V1])
    site_id = (await admin_client.post("/api/sites", json={"url": "https://example.test"})).json()[
        "id"
    ]
    response = await admin_client.post(f"/api/sites/{site_id}/snapshot")
    assert response.status_code == 200
    assert response.json()["status"] == "baseline"


async def test_notifications_audit_and_action_required(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    capturer.queue.extend([_V1, _V2])
    recipient_id = (
        await admin_client.post("/api/recipients", json={"email": "ops@example.com"})
    ).json()["id"]
    site_id = (
        await admin_client.post(
            "/api/sites", json={"url": "https://example.test", "recipient_ids": [recipient_id]}
        )
    ).json()["id"]

    await admin_client.post(f"/api/sites/{site_id}/check")  # baseline
    await admin_client.post(f"/api/sites/{site_id}/check")  # change -> significant -> notify

    audit = await admin_client.get("/api/notifications")
    assert audit.status_code == 200
    entries = audit.json()
    assert len(entries) == 1
    assert entries[0]["status"] == "sent"
    assert entries[0]["recipient_email"] == "ops@example.com"
    assert entries[0]["site_id"] == site_id

    # The stub analyzer succeeds, so nothing should be stuck needing action.
    action = await admin_client.get("/api/changes/action-required")
    assert action.json() == []


async def test_notifications_filter_by_change(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    _v3 = "<html><body><h1>Docs</h1><p>The third version of the page body</p></body></html>"
    capturer.queue.extend([_V1, _V2, _v3])
    recipient_id = (
        await admin_client.post("/api/recipients", json={"email": "ops@example.com"})
    ).json()["id"]
    site_id = (
        await admin_client.post(
            "/api/sites", json={"url": "https://example.test", "recipient_ids": [recipient_id]}
        )
    ).json()["id"]

    await admin_client.post(f"/api/sites/{site_id}/check")  # baseline
    await admin_client.post(f"/api/sites/{site_id}/check")  # first change -> one delivery
    await admin_client.post(f"/api/sites/{site_id}/check")  # second change -> another delivery

    changes = (await admin_client.get("/api/changes", params={"site_id": site_id})).json()
    assert len(changes) == 2
    change_id = changes[0]["id"]

    scoped = await admin_client.get("/api/notifications", params={"change_id": change_id})
    assert scoped.status_code == 200
    entries = scoped.json()
    assert len(entries) == 1
    assert all(entry["change_id"] == change_id for entry in entries)

    # An unknown change id matches nothing rather than falling back to the feed.
    empty = await admin_client.get("/api/notifications", params={"change_id": 99_999})
    assert empty.json() == []
