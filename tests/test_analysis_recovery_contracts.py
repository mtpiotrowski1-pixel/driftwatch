"""Analysis policy, ownership and recovery through the real runner."""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from tests.conftest import RecordingChannel, ScriptedCapturer, StubAnalyzer, create_org

from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.enums import AnalysisMode, AnalysisStatus, NotificationMode
from driftwatch.models import (
    AIUsage,
    AnalysisRun,
    ChangeEvent,
    Organization,
    Recipient,
    Site,
    Snapshot,
)
from driftwatch.monitoring.analyzer import Analysis
from driftwatch.runner import SiteRunner
from driftwatch.services import set_site_recipients


async def _change(
    database: Database, *, limit: int = 2, disabled: bool = False
) -> tuple[int, int, int]:
    async with database.session() as session:
        org_id = await create_org(session)
        organization = await session.get(Organization, org_id)
        assert organization is not None
        organization.monthly_ai_check_limit = limit
        site = Site(
            organization_id=org_id,
            url="https://example.test",
            notification_mode=NotificationMode.ALWAYS,
            analysis_mode=AnalysisMode.DISABLED if disabled else AnalysisMode.AI,
        )
        recipient = Recipient(organization_id=org_id, email="watcher@example.com")
        session.add_all([site, recipient])
        await session.flush()
        await set_site_recipients(session, site.id, [recipient.id])
        snapshot = Snapshot(
            site_id=site.id, content_html="<p>Basic 20 EUR</p>", content_text="Basic 20 EUR"
        )
        session.add(snapshot)
        await session.flush()
        change = ChangeEvent(
            site_id=site.id,
            new_snapshot_id=snapshot.id,
            diff_text="REMOVED Basic 10 EUR\nADDED Basic 20 EUR",
            ai_error="Previous analysis interrupted",
            analysis_status=AnalysisStatus.ERROR,
        )
        session.add(change)
        await session.commit()
        return site.id, change.id, org_id


async def test_disabled_ai_delivers_diff_without_key_or_quota(
    database: Database, settings: Settings
) -> None:
    site_id, change_id, org_id = await _change(database, limit=0, disabled=True)
    analyzer = StubAnalyzer(error="must never be called")
    channel = RecordingChannel()
    runner = SiteRunner(database, ScriptedCapturer(), settings, analyzer=analyzer, channel=channel)
    result = await runner.reprocess_change(change_id)
    assert result.site_id == site_id
    assert result.notified is True
    assert result.significant is None
    assert analyzer.calls == []
    assert len(channel.sent) == 1
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        organization = await session.get(Organization, org_id)
        assert change is not None and organization is not None
        assert change.analysis_status == AnalysisStatus.DISABLED
        assert organization.ai_checks_reserved == 0
        assert await session.scalar(select(func.count()).select_from(AIUsage)) == 0


async def test_quota_block_is_persisted_and_retried_after_limit_increase(
    database: Database, settings: Settings
) -> None:
    _, change_id, org_id = await _change(database, limit=0)
    analyzer = StubAnalyzer()
    runner = SiteRunner(
        database, ScriptedCapturer(), settings, analyzer=analyzer, channel=RecordingChannel()
    )
    result = await runner.reprocess_change(change_id)
    assert result.ai_error and "limit" in result.ai_error
    assert analyzer.calls == []
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        organization = await session.get(Organization, org_id)
        assert change is not None and organization is not None
        assert change.analysis_status == AnalysisStatus.QUOTA_BLOCKED
        assert change.ai_error and change.next_retry_at is not None
        assert change.analysis_lease_token is None
        organization.monthly_ai_check_limit = 1
        await session.commit()
    retried = await runner.reprocess_change(change_id)
    assert retried.notified and retried.significant is True
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        organization = await session.get(Organization, org_id)
        assert change is not None and organization is not None
        assert change.analysis_status == AnalysisStatus.SUCCEEDED
        assert change.ai_error is None and change.next_retry_at is None
        assert organization.ai_checks_reserved == 1


async def test_concurrent_retry_has_one_provider_call_and_one_reservation(
    database: Database, settings: Settings
) -> None:
    _, change_id, org_id = await _change(database)
    entered, release = asyncio.Event(), asyncio.Event()

    class ControlledAnalyzer(StubAnalyzer):
        async def analyze(
            self, *, diff_text: str, url: str, system_prompt: str, model: str
        ) -> Analysis:
            entered.set()
            await release.wait()
            return await super().analyze(
                diff_text=diff_text, url=url, system_prompt=system_prompt, model=model
            )

    analyzer = ControlledAnalyzer()
    channel = RecordingChannel()
    first_runner = SiteRunner(
        database, ScriptedCapturer(), settings, analyzer=analyzer, channel=channel
    )
    second_runner = SiteRunner(
        database, ScriptedCapturer(), settings, analyzer=analyzer, channel=channel
    )
    first = asyncio.create_task(first_runner.reprocess_change(change_id))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        second = await second_runner.reprocess_change(change_id)
        assert second.ai_error == "Analysis already in progress or completed"
    finally:
        release.set()
    assert (await first).notified
    assert len(analyzer.calls) == 1
    assert len(channel.sent) == 1
    async with database.session() as session:
        organization = await session.get(Organization, org_id)
        assert organization is not None and organization.ai_checks_reserved == 1
        assert await session.scalar(select(func.count()).select_from(AIUsage)) == 1
        assert await session.scalar(select(func.count()).select_from(AnalysisRun)) == 1
