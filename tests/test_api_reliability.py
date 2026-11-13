"""API tests for security headers, dry checks, snapshots, and the audit log."""

from __future__ import annotations

import httpx

from tests.conftest import RecordingChannel, ScriptedCapturer, StubAnalyzer

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


async def _site_with_recipient(client: httpx.AsyncClient) -> int:
    recipient = await client.post("/api/recipients", json={"email": "ops@example.com"})
    assert recipient.status_code == 201, recipient.text
    site = await client.post(
        "/api/sites",
        json={"url": "https://example.test", "recipient_ids": [recipient.json()["id"]]},
    )
    assert site.status_code == 201, site.text
    return int(site.json()["id"])


async def test_dry_check_records_the_change_without_analysis_or_delivery(
    admin_client: httpx.AsyncClient,
    capturer: ScriptedCapturer,
    analyzer: StubAnalyzer,
    channel: RecordingChannel,
) -> None:
    _v3 = "<html><body><h1>Docs</h1><p>The third version of the page body</p></body></html>"
    capturer.queue.extend([_V1, _V2, _v3])
    site_id = await _site_with_recipient(admin_client)
    check = f"/api/sites/{site_id}/check"

    assert (await admin_client.post(check, params={"analyze": "false"})).json()[
        "status"
    ] == "baseline"
    dry = await admin_client.post(check, params={"analyze": "false"})
    assert dry.json()["status"] == "changed"
    assert analyzer.calls == []
    assert channel.sent == []

    # Control: the same site is analyzed and delivered once analysis is requested.
    assert (await admin_client.post(check)).json()["status"] == "changed"
    assert len(analyzer.calls) == 1
    assert len(channel.sent) == 1

    changes = (await admin_client.get("/api/changes", params={"site_id": site_id})).json()
    statuses = sorted(change["analysis_status"] for change in changes)
    assert statuses == ["not_requested", "succeeded"]


async def test_snapshot_replaces_the_baseline_without_a_change(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    capturer.queue.extend([_V1, _V2, _V2])
    site_id = (await admin_client.post("/api/sites", json={"url": "https://example.test"})).json()[
        "id"
    ]
    assert (await admin_client.post(f"/api/sites/{site_id}/check")).json()["status"] == "baseline"

    snapshot = await admin_client.post(f"/api/sites/{site_id}/snapshot")
    assert snapshot.status_code == 200
    assert snapshot.json()["status"] == "baseline"

    # The next check compares against V2, so the page is unchanged.
    assert (await admin_client.post(f"/api/sites/{site_id}/check")).json()["status"] == "unchanged"
    changes = (await admin_client.get("/api/changes", params={"site_id": site_id})).json()
    assert changes == []


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


async def test_unparseable_ignore_selector_is_rejected_before_it_is_stored(
    admin_client: httpx.AsyncClient,
) -> None:
    rejected = await admin_client.post(
        "/api/sites", json={"url": "https://example.test", "ignore_selectors": ["div["]}
    )
    assert rejected.status_code == 422
    assert "Invalid CSS selector" in rejected.text

    accepted = await admin_client.post(
        "/api/sites", json={"url": "https://example.test", "ignore_selectors": [".banner"]}
    )
    assert accepted.status_code == 201, accepted.text


async def test_display_names_are_bounded_by_the_column_length(
    admin_client: httpx.AsyncClient,
) -> None:
    too_long = await admin_client.post(
        "/api/recipients", json={"email": "ops@example.com", "name": "x" * 201}
    )
    assert too_long.status_code == 422
    longest = await admin_client.post(
        "/api/recipients", json={"email": "ops@example.com", "name": "x" * 200}
    )
    assert longest.status_code == 201, longest.text


async def test_manual_check_prunes_with_the_retention_saved_in_settings(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    pages = [f"<main><p>Version {index} of the watched page body</p></main>" for index in range(4)]
    capturer.queue.extend(pages)
    saved = await admin_client.put("/api/settings", json={"snapshot_retention": 2})
    assert saved.status_code == 200, saved.text
    site_id = (await admin_client.post("/api/sites", json={"url": "https://example.test"})).json()[
        "id"
    ]

    for _ in pages:
        check = await admin_client.post(f"/api/sites/{site_id}/check", params={"analyze": "false"})
        assert check.status_code == 200, check.text

    # Keeping two snapshots keeps the two changes that end at them. The
    # environment default (much larger) would have kept all three.
    changes = (await admin_client.get("/api/changes", params={"site_id": site_id})).json()
    assert len(changes) == 2
