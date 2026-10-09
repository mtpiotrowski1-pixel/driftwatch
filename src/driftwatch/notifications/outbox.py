"""Transactional notification outbox and per-destination delivery worker.

Enqueue is committed before a provider is called. Each destination carries its
own retry state and short lease, so concurrent workers cannot normally deliver
the same row and a crashed worker becomes recoverable after lease expiry.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Literal
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.enums import (
    NotificationDeliveryStatus,
    NotificationStatus,
    RetryStatus,
)
from driftwatch.models import (
    ChangeEvent,
    NotificationDelivery,
    NotificationLog,
    NotificationOutbox,
)
from driftwatch.notifications.email import EmailChannel, EmailEnvelope, SendError
from driftwatch.notifications.webhook import WebhookError, WebhookEvent, send_webhook
from driftwatch.security.crypto import SecretBox
from driftwatch.settings_store import WebhookConfig

logger = logging.getLogger(__name__)

DeliveryKind = Literal["email", "webhook"]

_LEASE_SECONDS = 120
_RETRY_BACKOFF_MINUTES: tuple[int, ...] = (5, 15, 60, 240)
_PENDING_ERROR = "notification delivery is pending"


@dataclass(frozen=True, slots=True)
class DeliverySpec:
    kind: DeliveryKind
    destination_key: str
    destination_label: str
    payload: dict[str, object]
    target_ciphertext: str | None = None


@dataclass(frozen=True, slots=True)
class ClaimedDelivery:
    """Owned provider input, independent of an expiring ORM identity map."""

    id: int
    outbox_id: int
    change_id: int
    kind: str
    destination_label: str
    payload: dict[str, object]
    target_ciphertext: str | None
    idempotency_key: str
    attempt_count: int
    lease_token: str


def destination_key(kind: DeliveryKind, target: str) -> str:
    """Opaque stable fingerprint; webhook secrets never become index values."""
    return sha256(f"{kind}:{target}".encode()).hexdigest()


async def enqueue_notification(
    session: AsyncSession,
    change: ChangeEvent,
    specs: list[DeliverySpec],
    *,
    now: datetime | None = None,
) -> tuple[NotificationOutbox, bool]:
    """Create a change's outbox exactly once in the caller's transaction.

    The nested transaction handles two workers racing to enqueue the same
    change without rolling back the surrounding analysis transaction.
    """
    if change.id is None:
        raise ValueError("A persisted change is required before notification enqueue")
    idempotency_key = f"change:{change.id}:notification:v1"
    existing = await _outbox_by_key(session, idempotency_key)
    if existing is not None:
        return existing, False

    timestamp = now or datetime.now(UTC)
    outbox = NotificationOutbox(
        change_id=change.id,
        idempotency_key=idempotency_key,
        created_at=timestamp,
        completed_at=timestamp if not specs else None,
    )
    try:
        async with session.begin_nested():
            session.add(outbox)
            await session.flush()
            session.add_all(
                [
                    NotificationDelivery(
                        outbox_id=outbox.id,
                        destination_key=spec.destination_key,
                        idempotency_key=(f"{idempotency_key}:{spec.kind}:{spec.destination_key}"),
                        kind=spec.kind,
                        destination_label=spec.destination_label,
                        payload=spec.payload,
                        target_ciphertext=spec.target_ciphertext,
                        status=NotificationDeliveryStatus.PENDING,
                        attempt_count=0,
                        next_attempt_at=timestamp,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                    for spec in specs
                ]
            )
            await session.flush()
    except IntegrityError:
        existing = await _outbox_by_key(session, idempotency_key)
        if existing is None:
            raise
        return existing, False

    change.notified_at = None
    change.notification_retry_count = 0
    change.retry_status = None
    change.notification_error = _PENDING_ERROR if specs else None
    change.next_retry_at = timestamp if specs else None
    return outbox, True


async def dispatch_notification(
    session: AsyncSession,
    outbox_id: int,
    *,
    channel: EmailChannel,
    secret_box: SecretBox | None,
    now: datetime | None = None,
    lease_seconds: int = _LEASE_SECONDS,
    force: bool = False,
    clock: Callable[[], datetime] | None = None,
) -> list[NotificationLog]:
    """Deliver due destinations with a fresh lease and bounded provider I/O.

    Delivery is at least once: a crash after provider acceptance can require a
    retry. Stable provider idempotency keys mitigate that external ambiguity;
    database fencing prevents a former owner from overwriting a newer attempt.
    ``now`` freezes time for compatibility; ``clock`` controls advancing time.
    """
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    current_time = clock or (lambda: now if now is not None else datetime.now(UTC))
    if force:
        await _make_failed_destinations_due(session, outbox_id, now=current_time())
    logs: list[NotificationLog] = []
    while claimed := await _claim_next(
        session,
        outbox_id,
        now=current_time(),
        lease_seconds=lease_seconds,
    ):
        try:
            # Cancellation must precede lease expiry. A stuck provider should
            # not overlap a replacement worker's send indefinitely.
            async with asyncio.timeout(lease_seconds * 0.9):
                log = await _attempt_delivery(claimed, channel=channel, secret_box=secret_box)
        except TimeoutError:
            log = _failure_log(claimed, "notification provider timed out")
        if await _finish_attempt(session, claimed, log, now=current_time()):
            logs.append(log)

    await _synchronize_change(session, outbox_id, now=current_time())
    await session.commit()
    return logs


async def _outbox_by_key(session: AsyncSession, idempotency_key: str) -> NotificationOutbox | None:
    return (
        await session.execute(
            select(NotificationOutbox).where(NotificationOutbox.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()


async def _claim_next(
    session: AsyncSession,
    outbox_id: int,
    *,
    now: datetime,
    lease_seconds: int,
) -> ClaimedDelivery | None:
    lease_available = or_(
        NotificationDelivery.lease_token.is_(None),
        NotificationDelivery.lease_expires_at.is_(None),
        NotificationDelivery.lease_expires_at <= now,
    )
    due = or_(
        and_(
            NotificationDelivery.status == NotificationDeliveryStatus.PENDING,
            or_(
                NotificationDelivery.next_attempt_at.is_(None),
                NotificationDelivery.next_attempt_at <= now,
            ),
        ),
        and_(
            NotificationDelivery.status == NotificationDeliveryStatus.FAILED,
            NotificationDelivery.next_attempt_at.is_not(None),
            NotificationDelivery.next_attempt_at <= now,
        ),
    )
    candidate = (
        select(NotificationDelivery.id)
        .where(
            NotificationDelivery.outbox_id == outbox_id,
            NotificationDelivery.status != NotificationDeliveryStatus.SENT,
            lease_available,
            due,
        )
        .order_by(
            NotificationDelivery.next_attempt_at.asc().nulls_first(),
            NotificationDelivery.id.asc(),
        )
        .limit(1)
        .scalar_subquery()
    )
    token = str(uuid4())
    claimed = (
        await session.execute(
            update(NotificationDelivery)
            .where(
                NotificationDelivery.id == candidate,
                NotificationDelivery.status != NotificationDeliveryStatus.SENT,
                lease_available,
                due,
            )
            .values(
                lease_token=token,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                attempt_count=NotificationDelivery.attempt_count + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
            .returning(
                NotificationDelivery.id,
                NotificationDelivery.outbox_id,
                NotificationDelivery.kind,
                NotificationDelivery.destination_label,
                NotificationDelivery.payload,
                NotificationDelivery.target_ciphertext,
                NotificationDelivery.idempotency_key,
                NotificationDelivery.attempt_count,
            )
        )
    ).one_or_none()
    if claimed is None:
        await session.commit()
        return None
    change_id = await session.scalar(
        select(NotificationOutbox.change_id).where(NotificationOutbox.id == claimed.outbox_id)
    )
    assert change_id is not None
    delivery = ClaimedDelivery(
        id=claimed.id,
        outbox_id=claimed.outbox_id,
        change_id=change_id,
        kind=claimed.kind,
        destination_label=claimed.destination_label,
        payload=dict(claimed.payload),
        target_ciphertext=claimed.target_ciphertext,
        idempotency_key=claimed.idempotency_key,
        attempt_count=claimed.attempt_count,
        lease_token=token,
    )
    await session.commit()
    return delivery


async def _make_failed_destinations_due(
    session: AsyncSession, outbox_id: int, *, now: datetime
) -> None:
    """Give a user-requested retry one attempt without weakening auto backoff."""
    await session.execute(
        update(NotificationDelivery)
        .where(
            NotificationDelivery.outbox_id == outbox_id,
            NotificationDelivery.status == NotificationDeliveryStatus.FAILED,
        )
        .values(next_attempt_at=now, updated_at=now)
    )
    await session.commit()


async def _attempt_delivery(
    delivery: ClaimedDelivery,
    *,
    channel: EmailChannel,
    secret_box: SecretBox | None,
) -> NotificationLog:
    if delivery.kind == "email":
        return await _send_email(delivery, channel)
    if delivery.kind == "webhook":
        return await _send_webhook(delivery, secret_box)
    return _failure_log(delivery, "unsupported notification destination")


async def _send_email(delivery: ClaimedDelivery, channel: EmailChannel) -> NotificationLog:
    try:
        envelope = EmailEnvelope(
            to=_required_string(delivery.payload, "to"),
            to_name=_optional_string(delivery.payload, "to_name"),
            subject=_required_string(delivery.payload, "subject"),
            html_body=_required_string(delivery.payload, "html_body"),
            text_body=_required_string(delivery.payload, "text_body"),
            idempotency_key=delivery.idempotency_key,
        )
        message_id = await channel.send(envelope)
    except SendError:
        # SMTP/API exceptions can echo the recipient, response body, or message
        # metadata. The durable error is user-visible and retained, so keep it
        # deliberately generic just like webhook failures.
        return _failure_log(delivery, "email delivery failed", channel=str(channel.name))
    except Exception as exc:
        logger.warning(
            "unexpected email delivery failure for outbox row %s: error_type=%s",
            delivery.id,
            type(exc).__name__,
        )
        return _failure_log(
            delivery,
            "unexpected email delivery failure",
            channel=str(channel.name),
        )
    return NotificationLog(
        change_id=delivery.change_id,
        recipient_email=delivery.destination_label,
        channel=channel.name,
        status=NotificationStatus.SENT,
        message_id=message_id,
    )


async def _send_webhook(delivery: ClaimedDelivery, secret_box: SecretBox | None) -> NotificationLog:
    try:
        if secret_box is None or not delivery.target_ciphertext:
            raise ValueError("webhook credentials unavailable")
        target = secret_box.decrypt(delivery.target_ciphertext)
        if target is None:
            raise ValueError("webhook credentials unavailable")
        target_data = json.loads(target)
        if not isinstance(target_data, dict):
            raise ValueError("invalid webhook target")
        config = WebhookConfig(
            url=_required_string(target_data, "url"),
            format=_required_string(target_data, "format"),
        )
        event = WebhookEvent(
            site_label=_required_string(delivery.payload, "site_label"),
            site_url=_required_string(delivery.payload, "site_url"),
            headline=_required_string(delivery.payload, "headline"),
            summary=_required_string(delivery.payload, "summary"),
            significant=bool(delivery.payload.get("significant", False)),
            details_url=_required_string(delivery.payload, "details_url"),
            detected_at=_required_string(delivery.payload, "detected_at"),
        )
        await send_webhook(
            event,
            config,
            language=_required_string(delivery.payload, "language"),
            idempotency_key=delivery.idempotency_key,
        )
    except (WebhookError, TypeError, ValueError, json.JSONDecodeError):
        # A webhook URL can contain a bearer token. Provider exceptions may
        # echo it, so the durable feed intentionally stores a generic error.
        return _failure_log(delivery, "webhook delivery failed", channel="webhook")
    return NotificationLog(
        change_id=delivery.change_id,
        recipient_email=delivery.destination_label,
        channel="webhook",
        status=NotificationStatus.SENT,
    )


def _failure_log(
    delivery: ClaimedDelivery, error: str, *, channel: str | None = None
) -> NotificationLog:
    return NotificationLog(
        change_id=delivery.change_id,
        recipient_email=delivery.destination_label,
        channel=channel or delivery.kind,
        status=NotificationStatus.FAILED,
        error=error,
    )


async def _finish_attempt(
    session: AsyncSession,
    delivery: ClaimedDelivery,
    log: NotificationLog,
    *,
    now: datetime,
) -> bool:
    sent = log.status == NotificationStatus.SENT
    next_attempt = None if sent else _next_attempt(delivery.attempt_count, now)
    finalized_id = (
        await session.execute(
            update(NotificationDelivery)
            .where(
                NotificationDelivery.id == delivery.id,
                NotificationDelivery.lease_token == delivery.lease_token,
                NotificationDelivery.lease_expires_at > now,
            )
            .values(
                status=(
                    NotificationDeliveryStatus.SENT if sent else NotificationDeliveryStatus.FAILED
                ),
                next_attempt_at=next_attempt,
                lease_token=None,
                lease_expires_at=None,
                last_error=None if sent else log.error,
                provider_message_id=log.message_id if sent else None,
                sent_at=now if sent else None,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
            .returning(NotificationDelivery.id)
        )
    ).scalar_one_or_none()
    if finalized_id is None:
        # A failed CAS is not a transaction error. Committing the empty update
        # also avoids expiring unrelated caller objects through rollback.
        await session.commit()
        logger.warning("notification lease lost before row %s could be finalized", delivery.id)
        return False

    log.sent_at = now
    session.add(log)
    await _synchronize_change(session, delivery.outbox_id, now=now)
    await session.commit()
    return True


async def _synchronize_change(session: AsyncSession, outbox_id: int, *, now: datetime) -> None:
    outbox = await session.get(NotificationOutbox, outbox_id)
    if outbox is None:
        return
    change = await session.get(ChangeEvent, outbox.change_id)
    if change is None:
        return
    deliveries = (
        await session.execute(
            select(
                NotificationDelivery.status,
                NotificationDelivery.attempt_count,
                NotificationDelivery.next_attempt_at,
                NotificationDelivery.lease_expires_at,
                NotificationDelivery.last_error,
            ).where(NotificationDelivery.outbox_id == outbox_id)
        )
    ).all()

    if not deliveries:
        outbox.completed_at = outbox.completed_at or now
        change.notification_error = None
        change.notification_retry_count = 0
        if change.ai_error is None:
            change.next_retry_at = None
            change.retry_status = None
        return

    change.notification_retry_count = max(row.attempt_count for row in deliveries)
    if all(row.status == NotificationDeliveryStatus.SENT for row in deliveries):
        outbox.completed_at = outbox.completed_at or now
        change.notified_at = change.notified_at or now
        change.notification_error = None
        if change.ai_error is None:
            change.next_retry_at = None
            change.retry_status = None
        return

    outbox.completed_at = None
    unsent = [row for row in deliveries if row.status != NotificationDeliveryStatus.SENT]
    last_error = next((row.last_error for row in unsent if row.last_error), None)
    change.notification_error = (
        f"{len(unsent)} of {len(deliveries)} required notification destinations "
        f"remain undelivered{f': {last_error}' if last_error else ''}"
    )
    retry_at = [
        candidate
        for row in unsent
        if (
            candidate := _effective_retry_at(
                row.next_attempt_at,
                row.lease_expires_at,
                now,
            )
        )
        is not None
    ]
    if retry_at:
        change.next_retry_at = min(retry_at)
        change.retry_status = None
    else:
        change.next_retry_at = None
        change.retry_status = RetryStatus.REQUIRES_ACTION


def _next_attempt(attempt: int, now: datetime) -> datetime | None:
    if attempt > len(_RETRY_BACKOFF_MINUTES):
        return None
    return now + timedelta(minutes=_RETRY_BACKOFF_MINUTES[attempt - 1])


def _effective_retry_at(
    next_attempt_at: datetime | None,
    lease_expires_at: datetime | None,
    now: datetime,
) -> datetime | None:
    candidates = [value for value in (next_attempt_at, lease_expires_at) if value is not None]
    if not candidates:
        return None
    normalized = [_as_utc(value) for value in candidates]
    return max(now, *normalized)


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"outbox payload field {key!r} is invalid")
    return value


def _optional_string(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"outbox payload field {key!r} is invalid")


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
