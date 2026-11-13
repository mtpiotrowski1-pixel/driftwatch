"""Integration tests for the per-site pipeline over a real database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from driftwatch.db import Database
from driftwatch.enums import AnalysisStatus, NotificationMode
from driftwatch.models import AIUsage, ChangeEvent, Project, Site, Snapshot
from driftwatch.monitoring.pipeline import (
    CheckStatus,
    analyze_change,
    record_analysis_failure,
    resolve_notification_mode,
    run_check,
    should_notify,
)
from driftwatch.retention import prune_ai_usage, prune_site_history
from tests.conftest import ScriptedCapturer, StubAnalyzer, create_org

_PAGE_V1 = "<html><body><h1>Prices</h1><p>The widget costs 10 USD today</p></body></html>"
_PAGE_V2 = "<html><body><h1>Prices</h1><p>The widget costs 12 USD today</p></body></html>"


async def _make_site(database: Database, **overrides: object) -> int:
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(
            url="https://example.test/pricing",
            name="Pricing",
            organization_id=org_id,
            **overrides,
        )
        session.add(site)
        await session.flush()
        site_id = site.id
        await session.commit()
    return site_id


async def test_first_check_is_a_baseline(database: Database) -> None:
    site_id = await _make_site(database)
    capturer = ScriptedCapturer(html=_PAGE_V1)
    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        outcome = await run_check(session, site, capturer=capturer)
        await session.commit()

    assert outcome.status is CheckStatus.BASELINE
    async with database.session() as session:
        snapshots = (await session.execute(Snapshot.__table__.select())).all()
        changes = (await session.execute(ChangeEvent.__table__.select())).all()
    assert len(snapshots) == 1
    assert changes == []


async def test_unchanged_check_stores_no_new_snapshot(database: Database) -> None:
    site_id = await _make_site(database)
    capturer = ScriptedCapturer(queue=[_PAGE_V1, _PAGE_V1])
    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        await run_check(session, site, capturer=capturer)
        second = await run_check(session, site, capturer=capturer)
        await session.commit()

    assert second.status is CheckStatus.UNCHANGED
    async with database.session() as session:
        snapshots = (await session.execute(Snapshot.__table__.select())).all()
    assert len(snapshots) == 1


async def test_changed_check_creates_change_with_diff(database: Database) -> None:
    site_id = await _make_site(database)
    capturer = ScriptedCapturer(queue=[_PAGE_V1, _PAGE_V2])
    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        await run_check(session, site, capturer=capturer)
        outcome = await run_check(session, site, capturer=capturer)
        await session.commit()
        change = await session.get(ChangeEvent, outcome.change_id)

    assert outcome.status is CheckStatus.CHANGED
    assert change is not None
    assert "12 USD" in change.diff_text
    assert change.significant is None  # analysis has not run yet


async def test_analyze_change_records_verdict_and_usage(database: Database) -> None:
    change_id, site_id = await _seed_change(database)
    analyzer = StubAnalyzer(significant=True, headline="Price up", summary="10 to 12 USD")
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        site = await session.get(Site, site_id)
        assert change is not None and site is not None
        await analyze_change(
            session, change, site, analyzer=analyzer, system_prompt="rules", model="gpt-4o-mini"
        )
        await session.commit()

    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        usage = (await session.execute(AIUsage.__table__.select())).all()
    assert change is not None
    assert change.significant is True
    assert change.headline == "Price up"
    assert len(usage) == 1


async def test_failed_analysis_is_recorded_as_retryable(database: Database) -> None:
    change_id, _ = await _seed_change(database)
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        assert change is not None
        record_analysis_failure(change, "network error")
        await session.commit()

    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
    assert change is not None
    assert change.significant is None
    assert change.ai_error == "network error"
    assert change.ai_retry_count == 1


@pytest.mark.parametrize(
    ("significant", "mode", "expected"),
    [
        (True, NotificationMode.ONLY_SIGNIFICANT, True),
        (False, NotificationMode.ONLY_SIGNIFICANT, False),
        (False, NotificationMode.ALWAYS, True),
        (True, NotificationMode.ALWAYS, True),
    ],
)
def test_should_notify(significant: bool, mode: NotificationMode, expected: bool) -> None:
    assert should_notify(significant=significant, mode=mode) is expected


def test_resolve_notification_mode_prefers_site_then_project_then_default() -> None:
    project = Project(name="f", notification_mode=NotificationMode.ALWAYS)
    site = Site(url="x", notification_mode=NotificationMode.ONLY_SIGNIFICANT)
    assert resolve_notification_mode(site, project, NotificationMode.ALWAYS) is (
        NotificationMode.ONLY_SIGNIFICANT
    )

    site_no_mode = Site(url="x", notification_mode=None)
    assert resolve_notification_mode(site_no_mode, project, NotificationMode.ONLY_SIGNIFICANT) is (
        NotificationMode.ALWAYS
    )
    assert resolve_notification_mode(site_no_mode, None, NotificationMode.ALWAYS) is (
        NotificationMode.ALWAYS
    )


async def test_prune_site_history_keeps_recent_snapshots(database: Database) -> None:
    site_id = await _make_site(database)
    pages = [f"<p>Version number {index} of the watched content</p>" for index in range(6)]
    capturer = ScriptedCapturer(queue=pages)
    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        for _ in pages:
            outcome = await run_check(session, site, capturer=capturer)
            if outcome.change_id is not None:
                change = await session.get(ChangeEvent, outcome.change_id)
                assert change is not None
                # This fixture exercises resolved-history retention. Captures
                # whose analysis is still pending must survive pruning.
                change.analysis_status = AnalysisStatus.NOT_REQUESTED
        await session.commit()

    snapshots = select(Snapshot.id).where(Snapshot.site_id == site_id).order_by(Snapshot.id)
    async with database.session() as session:
        before = (await session.scalars(snapshots)).all()
        removed = await prune_site_history(session, site_id, keep=2)
        await session.commit()

    async with database.session() as session:
        after = (await session.scalars(snapshots)).all()
        changes = (
            await session.scalars(select(ChangeEvent).where(ChangeEvent.site_id == site_id))
        ).all()

    # The two newest snapshots are kept together with every change that ends at
    # one of them. The older side of those changes stays so each diff can still
    # be rebuilt, which keeps the third-newest snapshot too.
    assert len(before) == 6
    assert after == before[-3:]
    assert removed == 3
    assert sorted((change.old_snapshot_id, change.new_snapshot_id) for change in changes) == [
        (before[-3], before[-2]),
        (before[-2], before[-1]),
    ]


async def test_prune_ai_usage_drops_only_old_rows(database: Database) -> None:
    old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=400)
    async with database.session() as session:
        org_id = await create_org(session, "Usage retention")
        session.add(
            AIUsage(
                organization_id=org_id,
                model="gpt",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
                cost_usd=0.0,
                created_at=old,
            )
        )
        session.add(
            AIUsage(
                organization_id=org_id,
                model="gpt",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
                cost_usd=0.0,
            )
        )
        await session.commit()

    async with database.session() as session:
        removed = await prune_ai_usage(session, older_than_days=180)
        await session.commit()
    assert removed == 1

    async with database.session() as session:
        remaining = (await session.execute(AIUsage.__table__.select())).all()
    assert len(remaining) == 1


async def _seed_change(database: Database) -> tuple[int, int]:
    site_id = await _make_site(database)
    capturer = ScriptedCapturer(queue=[_PAGE_V1, _PAGE_V2])
    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        await run_check(session, site, capturer=capturer)
        outcome = await run_check(session, site, capturer=capturer)
        await session.commit()
        assert outcome.change_id is not None
        return outcome.change_id, site_id
