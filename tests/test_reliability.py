"""Retry lifecycle, change recovery, capture alerts, and URL validation."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.enums import NotificationStatus, RetryStatus
from driftwatch.exceptions import InvalidRequest
from driftwatch.models import ChangeEvent, NotificationLog, Recipient, Site, site_recipients
from driftwatch.monitoring.capture import CaptureSelectorMissing
from driftwatch.monitoring.pipeline import CheckStatus
from driftwatch.runner import SiteRunner
from driftwatch.security.urls import validate_public_url
from tests.conftest import RecordingChannel, ScriptedCapturer, StubAnalyzer, create_org

_V1 = "<html><body><h1>Prices</h1><p>The widget costs 10 USD today</p></body></html>"
_V2 = "<html><body><h1>Prices</h1><p>The widget costs 12 USD today</p></body></html>"


class RaisingCapturer:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def capture(self, **_: object) -> str:
        raise self._error


async def _add_site(database: Database, *, with_recipient: bool = False) -> int:
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(url="https://example.test/pricing", name="Pricing", organization_id=org_id)
        session.add(site)
        await session.flush()
        if with_recipient:
            recipient = Recipient(email="watch@example.com", active=True, organization_id=org_id)
            session.add(recipient)
            await session.flush()
            await session.execute(
                site_recipients.insert(),
                [{"site_id": site.id, "recipient_id": recipient.id}],
            )
        await session.commit()
        return site.id


async def test_failed_analysis_schedules_retry(
    database: Database, settings: Settings, channel: RecordingChannel
) -> None:
    capturer = ScriptedCapturer(queue=[_V1, _V2])
    runner = SiteRunner(
        database, capturer, settings, analyzer=StubAnalyzer(error="upstream down"), channel=channel
    )
    site_id = await _add_site(database, with_recipient=True)
    await runner.run(site_id)  # baseline
    result = await runner.run(site_id)  # change -> analysis fails

    assert result.ai_error == "upstream down"
    async with database.session() as session:
        change = (await session.execute(select(ChangeEvent))).scalar_one()
    assert change.significant is None
    assert change.ai_error == "upstream down"
    assert change.retry_status is None  # still auto-retryable
    assert change.next_retry_at is not None


async def test_reprocess_recovers_after_analyzer_returns(
    database: Database, settings: Settings, channel: RecordingChannel
) -> None:
    capturer = ScriptedCapturer(queue=[_V1, _V2])
    failing = SiteRunner(
        database, capturer, settings, analyzer=StubAnalyzer(error="x"), channel=channel
    )
    site_id = await _add_site(database, with_recipient=True)
    await failing.run(site_id)
    await failing.run(site_id)
    async with database.session() as session:
        change_id = (await session.execute(select(ChangeEvent.id))).scalar_one()

    healthy = SiteRunner(
        database, capturer, settings, analyzer=StubAnalyzer(significant=True), channel=channel
    )
    result = await healthy.reprocess_change(change_id)

    assert result.significant is True
    assert result.notified is True
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
    assert change is not None
    assert change.ai_error is None
    assert change.retry_status is None
    assert change.notified_at is not None
    assert len(channel.sent) == 1


async def test_no_recipients_skips_analysis_and_records_skip(
    database: Database, settings: Settings, channel: RecordingChannel
) -> None:
    """With nobody to deliver to, the runner must not bill the model — and the
    skip must land in the audit log rather than vanish."""
    capturer = ScriptedCapturer(queue=[_V1, _V2])
    analyzer = StubAnalyzer()
    runner = SiteRunner(database, capturer, settings, analyzer=analyzer, channel=channel)
    site_id = await _add_site(database)  # no recipients, no webhook configured

    await runner.run(site_id)  # baseline
    result = await runner.run(site_id)  # change

    assert result.status is CheckStatus.CHANGED
    assert analyzer.calls == []  # no AI spend for an undeliverable change
    assert channel.sent == []
    async with database.session() as session:
        change = (await session.execute(select(ChangeEvent))).scalar_one()
        logs = (await session.execute(select(NotificationLog))).scalars().all()
    assert change.significant is None
    assert change.ai_error is None and change.notification_error is None
    assert change.next_retry_at is None  # resolved, not queued for retry
    assert [log.status for log in logs] == [NotificationStatus.SKIPPED]


async def test_exhausted_retries_become_action_required(
    database: Database, settings: Settings, channel: RecordingChannel
) -> None:
    capturer = ScriptedCapturer(queue=[_V1, _V2])
    runner = SiteRunner(
        database, capturer, settings, analyzer=StubAnalyzer(error="x"), channel=channel
    )
    site_id = await _add_site(database, with_recipient=True)
    await runner.run(site_id)
    await runner.run(site_id)
    async with database.session() as session:
        change_id = (await session.execute(select(ChangeEvent.id))).scalar_one()

    # Re-run analysis until the backoff schedule is exhausted.
    for _ in range(5):
        await runner.reprocess_change(change_id)

    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
    assert change is not None
    assert change.retry_status == RetryStatus.REQUIRES_ACTION
    assert change.next_retry_at is None


async def test_capture_selector_missing_raises_throttled_alert(
    database: Database, settings: Settings, channel: RecordingChannel
) -> None:
    capturer = RaisingCapturer(CaptureSelectorMissing("gone"))
    runner = SiteRunner(database, capturer, settings, analyzer=StubAnalyzer(), channel=channel)
    site_id = await _add_site(database, with_recipient=True)

    first = await runner.run(site_id)
    assert first.capture_error is not None
    assert len(channel.sent) == 1
    assert "selector" in channel.sent[0].subject.lower()

    await runner.run(site_id)  # same alert within the window -> throttled
    assert len(channel.sent) == 1

    async with database.session() as session:
        site = await session.get(Site, site_id)
    assert site is not None
    assert site.last_alert_code == "selector_missing"


async def test_validate_public_url_accepts_public_https() -> None:
    assert await validate_public_url("https://example.com/pricing") == "https://example.com/pricing"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "https://service.internal/x",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://169.254.169.254/latest/meta-data",
        "http://100.64.0.1/",  # CGNAT / shared address space (RFC 6598)
        "ftp://example.com/file",
        "https://user:secret@example.com/report.pdf",
        "https://example.com:not-a-port/report.pdf",
        "https://[invalid-ipv6]/report.pdf",
    ],
)
async def test_validate_public_url_rejects_unsafe(url: str) -> None:
    with pytest.raises(InvalidRequest):
        await validate_public_url(url)


async def test_validate_public_url_fails_closed_on_unresolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import driftwatch.security.urls as urls

    async def empty(_host: str) -> list:
        return []

    monkeypatch.setattr(urls, "_resolve", empty)
    with pytest.raises(InvalidRequest):
        await validate_public_url("https://nonexistent.example/")
