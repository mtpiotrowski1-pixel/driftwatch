"""Human review of AI verdicts: endpoint access and the accuracy rollup."""

from __future__ import annotations

import httpx
from tests.conftest import ScriptedCapturer, create_org

from driftwatch.api.usage import verdict_accuracy
from driftwatch.db import Database
from driftwatch.models import ChangeEvent, Site, Snapshot

_PAGE_V1 = "<html><body><h1>Docs</h1><p>The first version of the page body</p></body></html>"
_PAGE_V2 = "<html><body><h1>Docs</h1><p>The second version of the page body</p></body></html>"


async def _analyzed_change(admin_client: httpx.AsyncClient, capturer: ScriptedCapturer) -> int:
    """Produce one change with an AI verdict (a recipient makes analysis run)."""
    recipient = await admin_client.post("/api/recipients", json={"email": "watch@example.com"})
    site = await admin_client.post(
        "/api/sites",
        json={"url": "https://example.test", "recipient_ids": [recipient.json()["id"]]},
    )
    site_id = site.json()["id"]
    capturer.queue.extend([_PAGE_V1, _PAGE_V2])
    await admin_client.post(f"/api/sites/{site_id}/check")
    changed = await admin_client.post(f"/api/sites/{site_id}/check")
    assert changed.json()["significant"] is True
    changes = await admin_client.get("/api/changes", params={"site_id": site_id})
    change_id: int = changes.json()[0]["id"]
    return change_id


async def test_verdict_set_and_clear(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    change_id = await _analyzed_change(admin_client, capturer)

    disagreed = await admin_client.post(
        f"/api/changes/{change_id}/verdict", json={"verdict": False}
    )
    assert disagreed.status_code == 200
    body = disagreed.json()
    assert body["user_verdict"] is False
    assert body["user_verdict_at"] is not None
    assert body["significant"] is True  # the AI's own verdict is untouched

    detail = await admin_client.get(f"/api/changes/{change_id}")
    assert detail.json()["user_verdict"] is False

    cleared = await admin_client.post(f"/api/changes/{change_id}/verdict", json={"verdict": None})
    assert cleared.json()["user_verdict"] is None
    assert cleared.json()["user_verdict_at"] is None


async def test_verdict_requires_edit_access(
    client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    await client.post(
        "/api/auth/register", json={"email": "admin@example.com", "password": "supersecret123"}
    )
    change_id = await _analyzed_change(client, capturer)

    # The second local registration joins the default org as a plain member with
    # no edit grants; reviewing a verdict demands site-edit access.
    await client.post(
        "/api/auth/register", json={"email": "member@example.com", "password": "supersecret123"}
    )
    denied = await client.post(f"/api/changes/{change_id}/verdict", json={"verdict": True})
    assert denied.status_code == 403


async def test_verdict_conflicts_without_ai_verdict(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    # No recipients -> the pre-AI short-circuit skips analysis, so there is no
    # verdict to agree or disagree with.
    site = await admin_client.post("/api/sites", json={"url": "https://example.test"})
    site_id = site.json()["id"]
    capturer.queue.extend([_PAGE_V1, _PAGE_V2])
    await admin_client.post(f"/api/sites/{site_id}/check")
    await admin_client.post(f"/api/sites/{site_id}/check")
    change_id = (await admin_client.get("/api/changes")).json()[0]["id"]

    response = await admin_client.post(f"/api/changes/{change_id}/verdict", json={"verdict": True})
    assert response.status_code == 409


async def test_verdict_rollup_endpoint(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    change_id = await _analyzed_change(admin_client, capturer)
    await admin_client.post(f"/api/changes/{change_id}/verdict", json={"verdict": False})

    summary = await admin_client.get("/api/usage/verdicts")
    assert summary.status_code == 200
    body = summary.json()
    assert body["reviewed"] == 1
    assert body["agreed"] == 0
    # The AI said significant and the human overrode it: a false positive.
    assert body["false_positives"] == 1
    assert body["false_negatives"] == 0
    assert body["agreement_rate"] == 0.0
    assert len(body["by_site"]) == 1
    assert body["by_site"][0]["reviewed"] == 1


async def test_verdict_accuracy_math(database: Database) -> None:
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(url="https://a.test", name="A", organization_id=org_id)
        session.add(site)
        await session.flush()
        snapshot = Snapshot(site_id=site.id, content_html="<p>x</p>")
        session.add(snapshot)
        await session.flush()

        def change(significant: bool | None, verdict: bool | None) -> ChangeEvent:
            return ChangeEvent(
                site_id=site.id,
                new_snapshot_id=snapshot.id,
                significant=significant,
                user_verdict=verdict,
            )

        session.add_all(
            [
                change(True, True),  # agreed
                change(True, False),  # false positive
                change(False, True),  # false negative
                change(True, None),  # not reviewed -> excluded
                change(None, True),  # no AI verdict -> excluded
            ]
        )
        await session.commit()

        buckets = await verdict_accuracy(session)

    assert len(buckets) == 1
    bucket = buckets[0]
    assert bucket.label == "A"
    assert (bucket.reviewed, bucket.agreed) == (3, 1)
    assert (bucket.false_positives, bucket.false_negatives) == (1, 1)
    assert bucket.agreement_rate == round(1 / 3, 4)
