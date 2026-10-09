"""Tests for recipient resolution and notification dispatch."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from tests.conftest import RecordingChannel, create_org

from driftwatch.db import Database
from driftwatch.enums import (
    EmailChannelName,
    NotificationDeliveryStatus,
    NotificationStatus,
)
from driftwatch.models import (
    ChangeEvent,
    NotificationDelivery,
    NotificationLog,
    NotificationOutbox,
    Project,
    Recipient,
    Site,
    Snapshot,
    project_recipients,
    site_recipients,
)
from driftwatch.notifications.dispatch import dispatch_change, resolve_recipients
from driftwatch.notifications.email import EmailEnvelope, SendError
from driftwatch.notifications.outbox import (
    ClaimedDelivery,
    DeliverySpec,
    _claim_next,
    destination_key,
    dispatch_notification,
    enqueue_notification,
)
from driftwatch.security.crypto import SecretBox
from driftwatch.settings_store import WebhookConfig


class FailOnceChannel:
    name = EmailChannelName.LOG

    def __init__(self, fail_once_for: str) -> None:
        self._remaining_failures = {fail_once_for: 1}
        self.attempts: list[EmailEnvelope] = []

    async def send(self, envelope: EmailEnvelope) -> str:
        self.attempts.append(envelope)
        remaining = self._remaining_failures.get(envelope.to, 0)
        if remaining:
            self._remaining_failures[envelope.to] = remaining - 1
            raise SendError("temporary provider failure")
        return f"msg-{len(self.attempts)}"


class CommitObservingChannel:
    name = EmailChannelName.LOG

    def __init__(self, database: Database) -> None:
        self._database = database
        self.observations = 0

    async def send(self, envelope: EmailEnvelope) -> str:
        async with self._database.session() as session:
            deliveries = (await session.execute(select(NotificationDelivery))).scalars().all()
        assert deliveries
        assert all(row.idempotency_key for row in deliveries)
        self.observations += 1
        return f"observed-{self.observations}"


async def _seed(database: Database) -> tuple[int, int]:
    """Create a site in a project with overlapping and inactive recipients."""
    async with database.session() as session:
        org_id = await create_org(session)
        project = Project(name="News", organization_id=org_id)
        active = Recipient(
            email="a@example.com", name="Active", active=True, organization_id=org_id
        )
        shared = Recipient(
            email="shared@example.com", name="Shared", active=True, organization_id=org_id
        )
        inactive = Recipient(
            email="off@example.com", name="Off", active=False, organization_id=org_id
        )
        session.add_all([project, active, shared, inactive])
        await session.flush()

        site = Site(
            url="https://example.test",
            name="Site",
            project_id=project.id,
            organization_id=org_id,
        )
        session.add(site)
        await session.flush()

        snapshot = Snapshot(site_id=site.id, content_html="<p>x</p>", content_text="x")
        session.add(snapshot)
        await session.flush()
        change = ChangeEvent(
            site_id=site.id,
            old_snapshot_id=None,
            new_snapshot_id=snapshot.id,
            diff_text="d",
            diff_html="<div></div>",
            significant=True,
            headline="Headline",
            summary="Summary",
        )
        session.add(change)
        await session.flush()

        await session.execute(
            site_recipients.insert(),
            [
                {"site_id": site.id, "recipient_id": active.id},
                {"site_id": site.id, "recipient_id": shared.id},
                {"site_id": site.id, "recipient_id": inactive.id},
            ],
        )
        await session.execute(
            project_recipients.insert(),
            [{"project_id": project.id, "recipient_id": shared.id}],
        )
        await session.commit()
        return site.id, change.id


async def test_resolve_recipients_dedupes_and_skips_inactive(database: Database) -> None:
    site_id, _ = await _seed(database)
    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        recipients = await resolve_recipients(session, site)
    emails = sorted(recipient.email for recipient in recipients)
    assert emails == ["a@example.com", "shared@example.com"]


async def test_dispatch_marks_change_notified_and_logs(database: Database) -> None:
    site_id, change_id = await _seed(database)
    channel = RecordingChannel()
    async with database.session() as session:
        site = await session.get(Site, site_id)
        change = await session.get(ChangeEvent, change_id)
        assert site is not None and change is not None
        logs = await dispatch_change(
            session, change, site, channel=channel, app_base_url="http://localhost:8000"
        )
        await session.commit()

    assert len(logs) == 2
    assert all(log.status is NotificationStatus.SENT for log in logs)
    assert len(channel.sent) == 2
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
    assert change is not None and change.notified_at is not None


async def test_dispatch_deep_links_to_the_exact_change(database: Database) -> None:
    site_id, change_id = await _seed(database)
    channel = RecordingChannel()
    async with database.session() as session:
        site = await session.get(Site, site_id)
        change = await session.get(ChangeEvent, change_id)
        assert site is not None and change is not None
        await dispatch_change(
            session, change, site, channel=channel, app_base_url="http://localhost:8000/"
        )
    assert channel.sent
    details_url = f"http://localhost:8000/sites/{site_id}?change={change_id}"
    assert details_url in channel.sent[0].text_body
    assert details_url in channel.sent[0].html_body


async def test_dispatch_renders_in_the_requested_language(database: Database) -> None:
    site_id, change_id = await _seed(database)
    channel = RecordingChannel()
    async with database.session() as session:
        site = await session.get(Site, site_id)
        change = await session.get(ChangeEvent, change_id)
        assert site is not None and change is not None
        await dispatch_change(
            session,
            change,
            site,
            channel=channel,
            app_base_url="http://localhost:8000",
            language="pl",
        )
    assert channel.sent
    assert channel.sent[0].text_body.startswith("Istotna zmiana")


async def test_dispatch_without_recipients_writes_a_skipped_audit_row(database: Database) -> None:
    channel = RecordingChannel()
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(url="https://example.test", organization_id=org_id)
        session.add(site)
        await session.flush()
        snapshot = Snapshot(site_id=site.id, content_html="<p>x</p>", content_text="x")
        session.add(snapshot)
        await session.flush()
        change = ChangeEvent(
            site_id=site.id, new_snapshot_id=snapshot.id, diff_text="d", diff_html=""
        )
        session.add(change)
        await session.flush()
        change_id = change.id

        logs = await dispatch_change(
            session, change, site, channel=channel, app_base_url="http://localhost:8000"
        )
        await session.commit()

    assert logs == []
    assert channel.sent == []
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        rows = (await session.execute(select(NotificationLog))).scalars().all()
    assert change is not None and change.notified_at is None
    assert len(rows) == 1
    assert rows[0].status == NotificationStatus.SKIPPED
    assert rows[0].change_id == change_id
    assert rows[0].error is not None


async def test_dispatch_records_failure_without_marking_notified(database: Database) -> None:
    site_id, change_id = await _seed(database)
    channel = RecordingChannel(fail=True)
    async with database.session() as session:
        site = await session.get(Site, site_id)
        change = await session.get(ChangeEvent, change_id)
        assert site is not None and change is not None
        logs = await dispatch_change(
            session, change, site, channel=channel, app_base_url="http://localhost:8000"
        )
        await session.commit()

    assert logs and all(log.status is NotificationStatus.FAILED for log in logs)
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
    assert change is not None and change.notified_at is None


async def test_outbox_is_committed_before_provider_side_effect(database: Database) -> None:
    site_id, change_id = await _seed(database)
    channel = CommitObservingChannel(database)
    async with database.session() as session:
        site = await session.get(Site, site_id)
        change = await session.get(ChangeEvent, change_id)
        assert site is not None and change is not None
        logs = await dispatch_change(
            session,
            change,
            site,
            channel=channel,
            app_base_url="http://localhost:8000",
        )

    assert len(logs) == 2
    assert channel.observations == 2


async def test_partial_success_retries_only_unsent_destination(database: Database) -> None:
    site_id, change_id = await _seed(database)
    channel = FailOnceChannel("shared@example.com")
    async with database.session() as session:
        site = await session.get(Site, site_id)
        change = await session.get(ChangeEvent, change_id)
        assert site is not None and change is not None
        first_logs = await dispatch_change(
            session,
            change,
            site,
            channel=channel,
            app_base_url="http://localhost:8000",
        )

    assert {log.status for log in first_logs} == {
        NotificationStatus.FAILED,
        NotificationStatus.SENT,
    }
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        deliveries = (
            (await session.execute(select(NotificationDelivery).order_by(NotificationDelivery.id)))
            .scalars()
            .all()
        )
        failed = next(row for row in deliveries if row.status == NotificationDeliveryStatus.FAILED)
        assert failed.last_error == "email delivery failed"
        assert "temporary provider failure" not in (change.notification_error or "")
        stable_key = failed.idempotency_key
        assert change is not None and change.notified_at is None
        failed.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    async with database.session() as session:
        site = await session.get(Site, site_id)
        change = await session.get(ChangeEvent, change_id)
        assert site is not None and change is not None
        retry_logs = await dispatch_change(
            session,
            change,
            site,
            channel=channel,
            app_base_url="http://localhost:8000",
        )

    assert [log.recipient_email for log in retry_logs] == ["shared@example.com"]
    assert [envelope.to for envelope in channel.attempts].count("a@example.com") == 1
    assert [envelope.to for envelope in channel.attempts].count("shared@example.com") == 2
    shared_keys = [
        envelope.idempotency_key
        for envelope in channel.attempts
        if envelope.to == "shared@example.com"
    ]
    assert shared_keys == [stable_key, stable_key]
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        states = (await session.execute(select(NotificationDelivery.status))).scalars().all()
    assert change is not None and change.notified_at is not None
    assert states == [NotificationDeliveryStatus.SENT, NotificationDeliveryStatus.SENT]


async def test_duplicate_enqueue_reuses_one_outbox_and_sends_nothing_twice(
    database: Database,
) -> None:
    site_id, change_id = await _seed(database)
    channel = RecordingChannel()
    for _ in range(2):
        async with database.session() as session:
            site = await session.get(Site, site_id)
            change = await session.get(ChangeEvent, change_id)
            assert site is not None and change is not None
            await dispatch_change(
                session,
                change,
                site,
                channel=channel,
                app_base_url="http://localhost:8000",
            )

    async with database.session() as session:
        outboxes = (await session.execute(select(NotificationOutbox))).scalars().all()
        deliveries = (await session.execute(select(NotificationDelivery))).scalars().all()
    assert len(outboxes) == 1
    assert len(deliveries) == 2
    assert len({row.idempotency_key for row in deliveries}) == 2
    assert len(channel.sent) == 2


async def test_webhook_outbox_encrypts_target_and_tracks_its_own_state(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    import driftwatch.notifications.outbox as outbox_module

    site_id, change_id = await _seed(database)
    captured: dict[str, object] = {}

    async def fake_send_webhook(
        _event: object,
        config: WebhookConfig,
        *,
        language: str,
        idempotency_key: str,
    ) -> None:
        captured.update(
            url=config.url,
            language=language,
            idempotency_key=idempotency_key,
        )

    monkeypatch.setattr(outbox_module, "send_webhook", fake_send_webhook)
    secret_box = SecretBox("test-outbox-secret")
    webhook_url = "https://hooks.example.com/private-token"
    async with database.session() as session:
        site = await session.get(Site, site_id)
        change = await session.get(ChangeEvent, change_id)
        assert site is not None and change is not None
        await dispatch_change(
            session,
            change,
            site,
            channel=RecordingChannel(),
            app_base_url="http://localhost:8000",
            webhook=WebhookConfig(url=webhook_url, format="slack"),
            secret_box=secret_box,
        )

    async with database.session() as session:
        webhook_delivery = (
            await session.execute(
                select(NotificationDelivery).where(NotificationDelivery.kind == "webhook")
            )
        ).scalar_one()
    assert webhook_delivery.status == NotificationDeliveryStatus.SENT
    assert webhook_delivery.target_ciphertext is not None
    assert webhook_url not in webhook_delivery.target_ciphertext
    assert captured == {
        "url": webhook_url,
        "language": "en",
        "idempotency_key": webhook_delivery.idempotency_key,
    }


async def test_expired_lease_recovers_delivery_after_worker_crash(database: Database) -> None:
    _, change_id = await _seed(database)
    started = datetime.now(UTC)
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        assert change is not None
        outbox, _ = await enqueue_notification(
            session,
            change,
            [
                DeliverySpec(
                    kind="email",
                    destination_key=destination_key("email", "crash@example.com"),
                    destination_label="crash@example.com",
                    payload={
                        "to": "crash@example.com",
                        "to_name": None,
                        "subject": "Crash recovery",
                        "html_body": "<p>Recovered</p>",
                        "text_body": "Recovered",
                    },
                )
            ],
            now=started,
        )
        await session.commit()
        outbox_id = outbox.id

    # Claim commits a lease and increments the attempt before the side effect.
    # Dropping the session now simulates a process crash before provider I/O.
    async with database.session() as session:
        claimed = await _claim_next(session, outbox_id, now=started, lease_seconds=60)
        assert claimed is not None

    channel = RecordingChannel()
    async with database.session() as session:
        before_expiry = await dispatch_notification(
            session,
            outbox_id,
            channel=channel,
            secret_box=None,
            now=started + timedelta(seconds=30),
        )
    assert before_expiry == []
    assert channel.sent == []

    async with database.session() as session:
        recovered = await dispatch_notification(
            session,
            outbox_id,
            channel=channel,
            secret_box=None,
            now=started + timedelta(seconds=61),
        )
    assert [log.status for log in recovered] == [NotificationStatus.SENT]
    async with database.session() as session:
        delivery = (await session.execute(select(NotificationDelivery))).scalar_one()
        change = await session.get(ChangeEvent, change_id)
    assert delivery.attempt_count == 2
    assert delivery.status == NotificationDeliveryStatus.SENT
    assert change is not None and change.notified_at is not None


async def test_atomic_claim_allows_only_one_worker_per_destination(database: Database) -> None:
    _, change_id = await _seed(database)
    now = datetime.now(UTC)
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        assert change is not None
        outbox, _ = await enqueue_notification(
            session,
            change,
            [
                DeliverySpec(
                    kind="email",
                    destination_key=destination_key("email", "once@example.com"),
                    destination_label="once@example.com",
                    payload={
                        "to": "once@example.com",
                        "to_name": None,
                        "subject": "Once",
                        "html_body": "<p>Once</p>",
                        "text_body": "Once",
                    },
                )
            ],
            now=now,
        )
        await session.commit()
        outbox_id = outbox.id

    async def claim() -> ClaimedDelivery | None:
        async with database.session() as session:
            return await _claim_next(session, outbox_id, now=now, lease_seconds=60)

    claims = await asyncio.gather(claim(), claim())
    assert sum(item is not None for item in claims) == 1


async def test_exhausted_delivery_stops_auto_retry_but_allows_one_manual_attempt(
    database: Database,
) -> None:
    site_id, change_id = await _seed(database)
    channel = RecordingChannel(fail=True)

    async def attempt(*, force: bool) -> None:
        async with database.session() as session:
            site = await session.get(Site, site_id)
            change = await session.get(ChangeEvent, change_id)
            assert site is not None and change is not None
            await dispatch_change(
                session,
                change,
                site,
                channel=channel,
                app_base_url="http://localhost:8000",
                force=force,
            )

    await attempt(force=False)
    for _ in range(4):
        await attempt(force=True)

    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        deliveries = (await session.execute(select(NotificationDelivery))).scalars().all()
    assert change is not None
    assert change.retry_status is not None
    assert change.next_retry_at is None
    assert {row.attempt_count for row in deliveries} == {5}
    assert all(row.next_attempt_at is None for row in deliveries)

    await attempt(force=False)
    async with database.session() as session:
        counts = (await session.execute(select(NotificationDelivery.attempt_count))).scalars().all()
    assert set(counts) == {5}

    await attempt(force=True)
    async with database.session() as session:
        counts = (await session.execute(select(NotificationDelivery.attempt_count))).scalars().all()
    assert set(counts) == {6}
