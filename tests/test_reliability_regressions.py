"""Failure contracts derived from crash, lease and retention counterexamples."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta, tzinfo

import httpx
import pytest
from sqlalchemy import select
from tests.conftest import RecordingChannel, StubAnalyzer, create_org

from driftwatch.account_mail import AccountEmailWorker
from driftwatch.check_queue import (
    DueSite,
    claim_next_check,
    complete_check,
    enqueue_scheduled_checks,
)
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.enums import (
    AccountEmailStatus,
    AnalysisStatus,
    CheckJobStatus,
    EmailChannelName,
    NotificationDeliveryStatus,
    NotificationStatus,
    RetryStatus,
)
from driftwatch.models import (
    AccountEmailJob,
    ChangeEvent,
    NotificationDelivery,
    NotificationLog,
    NotificationOutbox,
    OrgSetting,
    Recipient,
    Site,
    SiteCheckJob,
    Snapshot,
    User,
    site_recipients,
)
from driftwatch.monitoring.capture import CaptureError
from driftwatch.notifications.email import (
    EmailConfigurationError,
    EmailEnvelope,
    LogChannel,
    build_channel,
)
from driftwatch.notifications.outbox import (
    DeliverySpec,
    _claim_next,
    _finish_attempt,
    destination_key,
    dispatch_notification,
    enqueue_notification,
)
from driftwatch.retention import prune_site_history
from driftwatch.runner import SiteRunner
from driftwatch.settings_store import EmailConfig


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2030, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


async def _change(database: Database) -> tuple[int, int]:
    async with database.session() as session:
        organization_id = await create_org(session)
        site = Site(organization_id=organization_id, url="https://reliability.test")
        session.add(site)
        await session.flush()
        snapshot = Snapshot(
            site_id=site.id, content_html="<p>baseline</p>", content_text="baseline"
        )
        session.add(snapshot)
        await session.flush()
        change = ChangeEvent(site_id=site.id, new_snapshot_id=snapshot.id, significant=True)
        session.add(change)
        await session.commit()
        return site.id, change.id


async def _outbox(database: Database, change_id: int, count: int, now: datetime) -> int:
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        assert change is not None
        outbox, _ = await enqueue_notification(
            session,
            change,
            [
                DeliverySpec(
                    kind="email",
                    destination_key=destination_key("email", f"recipient-{index}@example.com"),
                    destination_label=f"recipient-{index}@example.com",
                    payload={
                        "to": f"recipient-{index}@example.com",
                        "subject": "Changed",
                        "html_body": "<p>Changed</p>",
                        "text_body": "Changed",
                    },
                )
                for index in range(count)
            ],
            now=now,
        )
        await session.commit()
        return outbox.id


async def test_slow_batch_gives_late_destination_a_fresh_lease(database: Database) -> None:
    _, change_id = await _change(database)
    clock = Clock()
    outbox_id = await _outbox(database, change_id, 10, clock())
    competitor = RecordingChannel()

    class SlowChannel(RecordingChannel):
        async def send(self, envelope: EmailEnvelope) -> str:
            message_id = await super().send(envelope)
            if len(self.sent) == 10:
                # Nine sends have consumed 126 seconds. A second worker must
                # not steal the tenth destination just because the batch began
                # more than one lease ago.
                assert clock() == datetime(2030, 1, 1, tzinfo=UTC) + timedelta(seconds=126)
                async with database.session() as competing_session:
                    await dispatch_notification(
                        competing_session,
                        outbox_id,
                        channel=competitor,
                        secret_box=None,
                        clock=clock,
                    )
            clock.advance(14)
            return message_id

    channel = SlowChannel()
    async with database.session() as session:
        logs = await dispatch_notification(
            session, outbox_id, channel=channel, secret_box=None, clock=clock
        )
    assert len(logs) == 10
    assert len(channel.sent) == 10
    assert competitor.sent == []
    async with database.session() as session:
        deliveries = (await session.scalars(select(NotificationDelivery))).all()
        change = await session.get(ChangeEvent, change_id)
        assert change is not None
        assert change.notified_at is not None
        assert change.notified_at.replace(tzinfo=UTC) == clock()
        assert all(delivery.attempt_count == 1 for delivery in deliveries)


async def test_replaced_delivery_owner_cannot_finalize_or_expire_caller_objects(
    database: Database,
) -> None:
    _, change_id = await _change(database)
    clock = Clock()
    outbox_id = await _outbox(database, change_id, 1, clock())
    async with database.session() as old_session:
        change = await old_session.get(ChangeEvent, change_id)
        assert change is not None
        first = await _claim_next(old_session, outbox_id, now=clock(), lease_seconds=30)
        assert first is not None
        clock.advance(31)
        async with database.session() as new_session:
            second = await _claim_next(new_session, outbox_id, now=clock(), lease_seconds=30)
            assert second is not None
            assert second.lease_token != first.lease_token
        stale_log = NotificationLog(
            change_id=change_id,
            recipient_email="recipient-0@example.com",
            channel="log",
            status=NotificationStatus.SENT,
            message_id="old-owner",
        )
        assert not await _finish_attempt(old_session, first, stale_log, now=clock())
        # Previously rollback expired this object, so this ordinary access
        # raised MissingGreenlet in the caller after lease loss.
        assert change.notified_at is None
    async with database.session() as session:
        delivery = await session.scalar(select(NotificationDelivery))
        assert delivery is not None
        assert delivery.lease_token == second.lease_token
        assert delivery.status == NotificationDeliveryStatus.PENDING
        assert (await session.scalars(select(NotificationLog))).all() == []


async def test_provider_that_never_returns_is_cancelled_before_lease_expires(
    database: Database,
) -> None:
    _, change_id = await _change(database)
    outbox_id = await _outbox(database, change_id, 1, datetime.now(UTC))
    cancelled = asyncio.Event()

    class StuckChannel:
        name = EmailChannelName.LOG

        async def send(self, envelope: EmailEnvelope) -> str:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
            return "unreachable"

    async with database.session() as session:
        logs = await dispatch_notification(
            session, outbox_id, channel=StuckChannel(), secret_box=None, lease_seconds=1
        )
    assert cancelled.is_set()
    assert [log.status for log in logs] == [NotificationStatus.FAILED]
    async with database.session() as session:
        delivery = await session.scalar(select(NotificationDelivery))
        assert delivery is not None
        assert delivery.last_error == "notification provider timed out"
        assert delivery.lease_token is None
        assert delivery.next_attempt_at is not None


async def test_unexpected_provider_error_does_not_leak_payload_to_logs(
    database: Database, caplog: pytest.LogCaptureFixture
) -> None:
    _, change_id = await _change(database)
    clock = Clock()
    outbox_id = await _outbox(database, change_id, 1, clock())

    class HostileProvider:
        name = EmailChannelName.BREVO

        async def send(self, envelope: EmailEnvelope) -> str:
            raise RuntimeError("provider echoed private-token-synthetic and recipient@example.com")

    with caplog.at_level(logging.WARNING, logger="driftwatch.notifications.outbox"):
        async with database.session() as session:
            logs = await dispatch_notification(
                session, outbox_id, channel=HostileProvider(), secret_box=None, clock=clock
            )
    assert [log.status for log in logs] == [NotificationStatus.FAILED]
    assert "error_type=RuntimeError" in caplog.text
    assert "private-token-synthetic" not in caplog.text
    assert "recipient@example.com" not in caplog.text


async def test_repeated_process_crashes_exhaust_check_attempt_budget(database: Database) -> None:
    async with database.session() as session:
        organization_id = await create_org(session)
        sites = [
            Site(organization_id=organization_id, url=f"https://crash-{index}.test")
            for index in range(2)
        ]
        session.add_all(sites)
        await session.flush()
        site_ids = [site.id for site in sites]
        clock = Clock()
        jobs = await enqueue_scheduled_checks(
            session,
            [DueSite(site_id, organization_id, None) for site_id in site_ids],
            now=clock(),
            limit=2,
            global_capacity=10,
            per_org_capacity=10,
        )
        await session.commit()

    claims = []
    for attempt in range(1, 4):
        async with database.session() as session:
            claim = await claim_next_check(session, now=clock(), lease_seconds=10, max_attempts=3)
        assert claim is not None and claim.id == jobs[0]
        assert claim.attempt_count == attempt
        claims.append(claim)
        clock.advance(11)
    async with database.session() as session:
        next_job = await claim_next_check(session, now=clock(), lease_seconds=10, max_attempts=3)
        assert next_job is not None and next_job.id == jobs[1]
        exhausted = await session.get(SiteCheckJob, jobs[0])
        assert exhausted is not None
        assert exhausted.status == CheckJobStatus.DEAD
        assert exhausted.attempt_count == 3
        assert exhausted.lease_token is None
        assert exhausted.completed_at is not None
        assert not await complete_check(session, claims[-1], result={"stale": True}, now=clock())


@pytest.mark.parametrize("channel_name", [EmailChannelName.BREVO, EmailChannelName.SMTP])
@pytest.mark.parametrize("blank", [None, "", "   "])
async def test_selected_incomplete_email_provider_never_reports_log_success(
    channel_name: EmailChannelName, blank: str | None
) -> None:
    channel = build_channel(
        EmailConfig(
            channel=channel_name,
            from_email="sender@example.com",
            from_name="Tests",
            brevo_api_key=blank,
            smtp_host=blank,
        )
    )
    assert channel.name == channel_name
    assert not isinstance(channel, LogChannel)
    with pytest.raises(EmailConfigurationError):
        await channel.send(
            EmailEnvelope(to="recipient@example.com", subject="Test", html_body="", text_body="")
        )


async def test_log_delivery_is_an_explicit_development_choice() -> None:
    channel = build_channel(
        EmailConfig(channel=EmailChannelName.LOG, from_email="sender@example.com", from_name="Test")
    )
    assert isinstance(channel, LogChannel)
    assert (
        await channel.send(
            EmailEnvelope(to="test@example.com", subject="", html_body="", text_body="")
        )
        == "logged"
    )


@pytest.mark.parametrize("provider", [EmailChannelName.SMTP, EmailChannelName.BREVO])
async def test_incomplete_provider_keeps_notification_pending_for_recovery(
    database: Database, provider: EmailChannelName
) -> None:
    _, change_id = await _change(database)
    clock = Clock()
    outbox_id = await _outbox(database, change_id, 1, clock())
    channel = build_channel(
        EmailConfig(channel=provider, from_email="sender@example.com", from_name="Test")
    )
    async with database.session() as session:
        logs = await dispatch_notification(
            session, outbox_id, channel=channel, secret_box=None, clock=clock
        )
    assert [log.status for log in logs] == [NotificationStatus.FAILED]
    assert [log.channel for log in logs] == [provider]
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        delivery = await session.scalar(select(NotificationDelivery))
        assert change is not None and delivery is not None
        assert change.notified_at is None
        assert change.notification_error is not None
        assert delivery.status == NotificationDeliveryStatus.FAILED
        assert delivery.next_attempt_at is not None
        assert delivery.provider_message_id is None


@pytest.mark.parametrize("provider", ["smtp", "brevo"])
async def test_account_mail_missing_provider_config_remains_recoverable(
    client: httpx.AsyncClient, database: Database, settings: Settings, provider: str
) -> None:
    response = await client.post(
        "/api/auth/register", json={"email": "missing@example.com", "password": "password123"}
    )
    assert response.status_code == 201
    client.cookies.clear()
    async with database.session() as session:
        user = await session.get(User, response.json()["id"])
        assert user is not None and user.organization_id is not None
        session.add(
            OrgSetting(organization_id=user.organization_id, key="email_channel", value=provider)
        )
        await session.commit()
    assert (
        await client.post("/api/auth/request-password-reset", json={"email": "missing@example.com"})
    ).status_code == 204
    worker = AccountEmailWorker(database, settings)
    assert await worker.drain(now=datetime.now(UTC)) == 1
    async with database.session() as session:
        job = await session.scalar(select(AccountEmailJob))
        assert job is not None
        assert job.status == AccountEmailStatus.PENDING
        assert job.provider_message_id is None
        assert job.last_error_code == "email_not_configured"


@pytest.mark.parametrize(
    "pending",
    [
        "ai",
        "quota",
        "action",
        "delivery",
        "pending",
        "processing",
        "error",
        "quota_blocked",
        "lease",
    ],
)
async def test_retention_preserves_unfinished_work_and_both_diff_snapshots(
    database: Database, pending: str
) -> None:
    async with database.session() as session:
        organization_id = await create_org(session)
        site = Site(organization_id=organization_id, url="https://retention.test")
        session.add(site)
        await session.flush()
        snapshots = [
            Snapshot(site_id=site.id, content_html=f"<p>{index}</p>", content_text=str(index))
            for index in range(4)
        ]
        session.add_all(snapshots)
        await session.flush()
        unfinished = ChangeEvent(
            site_id=site.id,
            old_snapshot_id=snapshots[0].id,
            new_snapshot_id=snapshots[1].id,
            significant=True if pending == "delivery" else None,
        )
        if pending == "ai":
            unfinished.ai_error = "AI temporarily unavailable"
            unfinished.next_retry_at = datetime.now(UTC) + timedelta(minutes=5)
        elif pending == "quota":
            unfinished.ai_error = "Monthly analysis quota reached"
        elif pending == "action":
            unfinished.retry_status = RetryStatus.REQUIRES_ACTION
        elif pending in ("pending", "processing", "error", "quota_blocked"):
            unfinished.analysis_status = AnalysisStatus(pending)
        elif pending == "lease":
            unfinished.analysis_status = AnalysisStatus.SUCCEEDED
            unfinished.analysis_lease_token = "active-analysis-owner"
            unfinished.analysis_lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
        resolved = ChangeEvent(
            site_id=site.id,
            old_snapshot_id=snapshots[1].id,
            new_snapshot_id=snapshots[2].id,
            significant=False,
        )
        session.add_all([unfinished, resolved])
        await session.flush()
        if pending == "delivery":
            await enqueue_notification(
                session,
                unfinished,
                [
                    DeliverySpec(
                        kind="email",
                        destination_key=destination_key("email", "pending@example.com"),
                        destination_label="pending@example.com",
                        payload={"to": "pending@example.com"},
                    )
                ],
            )
            # Deliberately clear denormalized retry/error fields: the durable
            # outbox alone must be enough to protect the delivery intent.
            unfinished.notification_error = None
            unfinished.next_retry_at = None
        await session.commit()
        site_id, unfinished_id, resolved_id = site.id, unfinished.id, resolved.id
        protected_snapshot_ids = [snapshots[0].id, snapshots[1].id, snapshots[3].id]
    async with database.session() as session:
        await prune_site_history(session, site_id, keep=1)
        await session.commit()
    async with database.session() as session:
        assert await session.get(ChangeEvent, unfinished_id) is not None
        assert await session.get(ChangeEvent, resolved_id) is None
        assert (
            list(await session.scalars(select(Snapshot.id).order_by(Snapshot.id)))
            == protected_snapshot_ids
        )
        if pending == "delivery":
            assert await session.scalar(select(NotificationOutbox.id)) is not None
            assert await session.scalar(select(NotificationDelivery.id)) is not None


async def test_resolved_notification_history_can_eventually_be_pruned(database: Database) -> None:
    site_id, change_id = await _change(database)
    clock = Clock()
    outbox_id = await _outbox(database, change_id, 1, clock())
    async with database.session() as session:
        await dispatch_notification(
            session, outbox_id, channel=RecordingChannel(), secret_box=None, clock=clock
        )
        session.add(Snapshot(site_id=site_id, content_html="<p>latest</p>", content_text="latest"))
        await session.commit()
        await prune_site_history(session, site_id, keep=1)
        await session.commit()
    async with database.session() as session:
        assert await session.get(ChangeEvent, change_id) is None
        assert await session.scalar(select(NotificationOutbox.id)) is None
        assert await session.scalar(select(NotificationDelivery.id)) is None


async def _alert_site(database: Database) -> int:
    site_id, _ = await _change(database)
    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        recipient = Recipient(organization_id=site.organization_id, email="operations@example.com")
        session.add(recipient)
        await session.flush()
        await session.execute(
            site_recipients.insert().values(site_id=site_id, recipient_id=recipient.id)
        )
        session.add(
            OrgSetting(
                organization_id=site.organization_id,
                key="site_down_failure_threshold",
                value="50",
            )
        )
        await session.commit()
    return site_id


class FailedCapturer:
    async def capture(self, **_: object) -> str:
        raise CaptureError("connection refused")


async def test_suppressed_alerts_do_not_extend_the_six_hour_window(
    database: Database, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()

    class ControlledDateTime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return clock().astimezone(tz) if tz is not None else clock().replace(tzinfo=None)

    monkeypatch.setattr("driftwatch.runner.datetime", ControlledDateTime)
    site_id = await _alert_site(database)
    channel = RecordingChannel()
    runner = SiteRunner(
        database, FailedCapturer(), settings, analyzer=StubAnalyzer(), channel=channel
    )
    await runner.run(site_id)
    assert len(channel.sent) == 1
    for _ in range(2):
        clock.advance(2 * 60 * 60)
        await runner.run(site_id)
        assert len(channel.sent) == 1
        async with database.session() as session:
            site = await session.get(Site, site_id)
            assert site is not None
            assert site.last_alert_at is not None
            assert site.last_alert_at.replace(tzinfo=UTC) == datetime(2030, 1, 1, tzinfo=UTC)
    clock.advance(2 * 60 * 60)
    await runner.run(site_id)
    assert len(channel.sent) == 2
    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        assert site.last_alert_at is not None
        assert site.last_alert_at.replace(tzinfo=UTC) == datetime(2030, 1, 1, 6, tzinfo=UTC)
        assert site.consecutive_failure_count == 4


async def test_failed_operational_alert_does_not_throttle_next_attempt(
    database: Database, settings: Settings
) -> None:
    site_id = await _alert_site(database)
    channel = RecordingChannel(fail=True)
    runner = SiteRunner(
        database, FailedCapturer(), settings, analyzer=StubAnalyzer(), channel=channel
    )
    await runner.run(site_id)
    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        assert site.last_alert_at is None
    healthy_channel = RecordingChannel()
    recovered = SiteRunner(
        database, FailedCapturer(), settings, analyzer=StubAnalyzer(), channel=healthy_channel
    )
    await recovered.run(site_id)
    assert len(healthy_channel.sent) == 1
