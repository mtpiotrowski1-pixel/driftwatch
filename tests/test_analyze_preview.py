"""Dry-running draft AI rules against a past change: no persistence, quota gate."""

from __future__ import annotations

import httpx
from tests.conftest import ScriptedCapturer, StubAnalyzer

_PAGE_V1 = "<html><body><h1>Docs</h1><p>The first version of the page body</p></body></html>"
_PAGE_V2 = "<html><body><h1>Docs</h1><p>The second version of the page body</p></body></html>"

_RULES = "Only price changes are significant."


async def _unanalyzed_change(admin_client: httpx.AsyncClient, capturer: ScriptedCapturer) -> int:
    """A change without an AI verdict (no recipients -> analysis short-circuits)."""
    site = await admin_client.post("/api/sites", json={"url": "https://example.test"})
    site_id = site.json()["id"]
    capturer.queue.extend([_PAGE_V1, _PAGE_V2])
    await admin_client.post(f"/api/sites/{site_id}/check")
    await admin_client.post(f"/api/sites/{site_id}/check")
    change_id: int = (await admin_client.get("/api/changes")).json()[0]["id"]
    return change_id


async def test_preview_returns_verdict_without_persisting(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer, analyzer: StubAnalyzer
) -> None:
    change_id = await _unanalyzed_change(admin_client, capturer)

    response = await admin_client.post(
        f"/api/changes/{change_id}/analyze-preview", json={"rules": _RULES}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["significant"] is True  # the stub's fixed verdict
    assert body["headline"] == "Headline"
    assert body["summary"] == "Summary"

    # The draft rules (tagged as such) reached the model...
    assert "source: draft" in analyzer.calls[-1]
    assert _RULES in analyzer.calls[-1]

    # ...but nothing was written to the change itself.
    detail = (await admin_client.get(f"/api/changes/{change_id}")).json()
    assert detail["significant"] is None
    assert detail["headline"] is None
    assert detail["summary"] is None

    # The dry-run bills the model, so it is accounted like any analysis.
    summary = (await admin_client.get("/api/usage/summary")).json()
    assert summary["calls"] == 1


async def test_preview_respects_ai_quota(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer, analyzer: StubAnalyzer
) -> None:
    change_id = await _unanalyzed_change(admin_client, capturer)

    org_id = (await admin_client.get("/api/organizations")).json()[0]["id"]
    step_up = await admin_client.post("/api/auth/step-up", json={"password": "supersecret123"})
    assert step_up.status_code == 204, step_up.text
    capped = await admin_client.patch(
        f"/api/organizations/{org_id}", json={"monthly_ai_check_limit": 0}
    )
    assert capped.status_code == 200

    response = await admin_client.post(
        f"/api/changes/{change_id}/analyze-preview", json={"rules": _RULES}
    )
    assert response.status_code == 403
    assert analyzer.calls == []  # the gate fires before the model is called


async def test_preview_requires_rules_text(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    change_id = await _unanalyzed_change(admin_client, capturer)
    response = await admin_client.post(
        f"/api/changes/{change_id}/analyze-preview", json={"rules": ""}
    )
    assert response.status_code == 422
