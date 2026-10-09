"""Analysis history: every successful analysis appends a run, pruning cascades."""

from __future__ import annotations

import httpx
from sqlalchemy import select

from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.models import AnalysisRun, ChangeEvent, Recipient, Site, site_recipients
from driftwatch.retention import prune_site_history
from driftwatch.runner import SiteRunner
from tests.conftest import RecordingChannel, ScriptedCapturer, StubAnalyzer, create_org

_PAGES = [
    f"<html><body><h1>Docs</h1><p>Version number {index} of the body text</p></body></html>"
    for index in range(4)
]


async def _site_with_recipient(database: Database) -> int:
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(url="https://example.test/docs", name="Docs", organization_id=org_id)
        session.add(site)
        await session.flush()
        recipient = Recipient(email="watch@example.com", active=True, organization_id=org_id)
        session.add(recipient)
        await session.flush()
        await session.execute(
            site_recipients.insert(), [{"site_id": site.id, "recipient_id": recipient.id}]
        )
        await session.commit()
        return site.id


async def test_reanalyze_appends_run_and_keeps_history(
    database: Database, settings: Settings, channel: RecordingChannel
) -> None:
    capturer = ScriptedCapturer(queue=_PAGES[:2])
    first = SiteRunner(
        database,
        capturer,
        settings,
        analyzer=StubAnalyzer(significant=True, headline="First verdict"),
        channel=channel,
    )
    site_id = await _site_with_recipient(database)
    await first.run(site_id)  # baseline
    result = await first.run(site_id)  # change -> analysis #1
    assert result.change_id is not None
    change_id = result.change_id

    second = SiteRunner(
        database,
        capturer,
        settings,
        analyzer=StubAnalyzer(significant=False, headline="Second verdict"),
        channel=channel,
    )
    await second.analyze_only(change_id)

    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        runs = (
            (
                await session.execute(
                    select(AnalysisRun)
                    .where(AnalysisRun.change_id == change_id)
                    .order_by(AnalysisRun.id)
                )
            )
            .scalars()
            .all()
        )

    assert change is not None
    assert change.headline == "Second verdict"  # the change carries the latest
    assert [run.headline for run in runs] == ["First verdict", "Second verdict"]
    assert [run.significant for run in runs] == [True, False]


async def test_history_exposed_in_change_detail(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer
) -> None:
    recipient = await admin_client.post("/api/recipients", json={"email": "w@example.com"})
    site = await admin_client.post(
        "/api/sites",
        json={"url": "https://example.test", "recipient_ids": [recipient.json()["id"]]},
    )
    site_id = site.json()["id"]
    capturer.queue.extend(_PAGES[:2])
    await admin_client.post(f"/api/sites/{site_id}/check")
    await admin_client.post(f"/api/sites/{site_id}/check")
    change_id = (await admin_client.get("/api/changes")).json()[0]["id"]

    await admin_client.post(f"/api/changes/{change_id}/analyze")

    detail = (await admin_client.get(f"/api/changes/{change_id}")).json()
    runs = detail["analysis_runs"]
    assert len(runs) == 2
    # Newest first: the head mirrors the verdict on the change itself.
    assert runs[0]["id"] > runs[1]["id"]
    assert runs[0]["headline"] == detail["headline"]


async def test_pruning_changes_cascades_their_runs(
    database: Database, settings: Settings, channel: RecordingChannel
) -> None:
    capturer = ScriptedCapturer(queue=list(_PAGES))
    runner = SiteRunner(database, capturer, settings, analyzer=StubAnalyzer(), channel=channel)
    site_id = await _site_with_recipient(database)
    for _ in _PAGES:  # baseline + three analyzed changes
        await runner.run(site_id)

    async with database.session() as session:
        runs_before = (await session.execute(select(AnalysisRun))).scalars().all()
        assert len(runs_before) == 3
        await prune_site_history(session, site_id, keep=1)
        await session.commit()

    async with database.session() as session:
        surviving_changes = (await session.execute(select(ChangeEvent.id))).scalars().all()
        surviving_runs = (await session.execute(select(AnalysisRun))).scalars().all()

    assert len(surviving_changes) == 1
    # The pruned changes took their history with them (ON DELETE CASCADE);
    # only the surviving change's run remains.
    assert [run.change_id for run in surviving_runs] == surviving_changes
