"""Consecutive capture failures: counter, detail, and the one-shot down alert."""

from __future__ import annotations

import json

import httpx
from tests.conftest import RecordingChannel, ScriptedCapturer, StubAnalyzer, create_org

from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.models import OrgSetting, Recipient, Setting, Site, site_recipients
from driftwatch.monitoring.capture import CaptureError
from driftwatch.runner import SiteRunner

_PAGE = "<html><body><h1>Docs</h1><p>The body of the watched page</p></body></html>"


class RaisingCapturer:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def capture(self, **_: object) -> str:
        raise self._error


async def _add_site(database: Database, *, threshold: str | None = None) -> int:
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
        if threshold is not None:
            session.add(Setting(key="site_down_failure_threshold", value=threshold))
        await session.commit()
        return site.id


async def test_failure_counter_increments_and_resets_on_success(
    database: Database, settings: Settings, channel: RecordingChannel
) -> None:
    site_id = await _add_site(database)
    failing = SiteRunner(
        database,
        RaisingCapturer(CaptureError("dns lookup failed")),
        settings,
        analyzer=StubAnalyzer(),
        channel=channel,
    )
    await failing.run(site_id)
    await failing.run(site_id)

    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        assert site.consecutive_failure_count == 2
        assert site.last_alert_detail == "dns lookup failed"

    healthy = SiteRunner(
        database, ScriptedCapturer(html=_PAGE), settings, analyzer=StubAnalyzer(), channel=channel
    )
    await healthy.run(site_id)

    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        assert site.consecutive_failure_count == 0
        assert site.last_alert_detail is None
        assert site.last_alert_code is None


async def test_threshold_crossing_escalates_once_past_the_throttle(
    database: Database, settings: Settings, channel: RecordingChannel
) -> None:
    site_id = await _add_site(database, threshold="2")
    runner = SiteRunner(
        database,
        RaisingCapturer(CaptureError("connection refused")),
        settings,
        analyzer=StubAnalyzer(),
        channel=channel,
    )

    # Failure 1: the ordinary capture alert (first of its code, not throttled).
    await runner.run(site_id)
    assert len(channel.sent) == 1
    assert "down" not in channel.sent[0].subject.lower()

    # Failure 2 crosses the threshold: the stronger alert bypasses the 6h
    # throttle exactly once.
    await runner.run(site_id)
    assert len(channel.sent) == 2
    assert "site appears to be down" in channel.sent[1].subject.lower()
    assert "connection refused" in channel.sent[1].text_body

    # Failure 3 is past the crossing: the normal throttle applies again.
    await runner.run(site_id)
    assert len(channel.sent) == 2

    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        assert site.consecutive_failure_count == 3


async def test_alert_detail_exposed_in_site_api(admin_client: httpx.AsyncClient) -> None:
    site = await admin_client.post("/api/sites", json={"url": "https://example.test"})
    body = site.json()
    assert body["last_alert_detail"] is None
    assert body["consecutive_failure_count"] == 0


async def test_legacy_technical_alert_setting_cannot_cross_tenant_boundary(
    database: Database, settings: Settings, channel: RecordingChannel
) -> None:
    async with database.session() as session:
        org_id = await create_org(session, "Alert owner")
        foreign_org_id = await create_org(session, "Foreign tenant")
        site = Site(url="https://example.test/legacy", name="Legacy", organization_id=org_id)
        recipients = [
            Recipient(email="Ops@Example.com", active=True, organization_id=org_id),
            Recipient(email="ops@example.com", active=True, organization_id=org_id),
            Recipient(email="inactive@example.com", active=False, organization_id=org_id),
            Recipient(
                email="foreign-secret@example.com",
                active=True,
                organization_id=foreign_org_id,
            ),
        ]
        session.add_all([site, *recipients])
        await session.flush()
        session.add(
            OrgSetting(
                organization_id=org_id,
                key="technical_alert_recipient_ids",
                value=json.dumps(
                    [
                        recipients[3].id,
                        recipients[0].id,
                        recipients[1].id,
                        recipients[2].id,
                        recipients[0].id,
                    ]
                ),
            )
        )
        await session.commit()
        site_id = site.id

    runner = SiteRunner(
        database,
        RaisingCapturer(CaptureError("connection refused")),
        settings,
        analyzer=StubAnalyzer(),
        channel=channel,
    )
    await runner.run(site_id)

    assert [envelope.to for envelope in channel.sent] == ["Ops@Example.com"]
