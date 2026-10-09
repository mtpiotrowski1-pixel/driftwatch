"""Durable delivery of password-reset and account-invitation email.

Requests are persisted before an API response is committed. A scheduler worker
leases due rows and resolves the current account, tenant delivery settings, and
token generation only immediately before calling the provider. Neither email
addresses nor secret-bearing message bodies are stored in the queue.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.enums import AccountEmailKind, AccountEmailStatus, EmailChannelName
from driftwatch.models import AccountEmailJob, User
from driftwatch.notifications.email import (
    EmailChannel,
    EmailConfigurationError,
    EmailEnvelope,
    LogChannel,
    SendError,
    build_channel,
    default_sender_email,
)
from driftwatch.notifications.render import (
    render_account_invite_email,
    render_password_reset_email,
)
from driftwatch.security.crypto import SecretBox
from driftwatch.security.tokens import PURPOSE_PASSWORD_RESET, issue_scoped_token
from driftwatch.settings_store import SettingsStore

logger = logging.getLogger(__name__)

PASSWORD_RESET_TTL_SECONDS = 30 * 60
ACCOUNT_INVITATION_TTL_SECONDS = 24 * 60 * 60

_LEASE_SECONDS = 120
_MAX_ATTEMPTS = 5
_ANONYMOUS_CANCEL_RETENTION = timedelta(days=1)
_RETRY_BACKOFF: tuple[timedelta, ...] = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
)


@dataclass(frozen=True, slots=True)
class ClaimedAccountEmail:
    id: int
    user_id: int | None
    organization_id: int | None
    kind: AccountEmailKind
    idempotency_key: str
    attempt_count: int
    lease_token: str
    lease_expires_at: datetime


@dataclass(frozen=True, slots=True)
class _DeliveryResult:
    state: str
    token_expires_at: datetime | None = None
    provider_message_id: str | None = None
    error_code: str | None = None


async def enqueue_password_reset(
    session: AsyncSession,
    *,
    requested_email: str,
    user: User | None,
    secret: str,
    now: datetime | None = None,
) -> tuple[AccountEmailJob, bool]:
    """Persist a reset request without revealing whether ``user`` exists.

    Missing and inactive accounts use the same pending queue path as valid
    accounts. The worker later cancels an unresolvable target without ever
    storing the requested address.
    """
    active_key = _address_key(
        secret,
        kind=AccountEmailKind.PASSWORD_RESET,
        email=requested_email,
    )
    return await _enqueue(
        session,
        kind=AccountEmailKind.PASSWORD_RESET,
        user=user,
        active_key=active_key,
        now=now,
    )


async def enqueue_account_invitation(
    session: AsyncSession,
    *,
    user: User,
    now: datetime | None = None,
) -> tuple[AccountEmailJob, bool]:
    """Persist one active invitation per account, coalescing request retries."""
    if user.id is None:
        raise ValueError("A persisted user is required before invitation enqueue")
    active_key = sha256(f"account-invitation:user:{user.id}".encode()).hexdigest()
    return await _enqueue(
        session,
        kind=AccountEmailKind.ACCOUNT_INVITATION,
        user=user,
        active_key=active_key,
        now=now,
    )


async def _enqueue(
    session: AsyncSession,
    *,
    kind: AccountEmailKind,
    user: User | None,
    active_key: str,
    now: datetime | None,
) -> tuple[AccountEmailJob, bool]:
    existing = await _active_job(session, kind=kind, active_key=active_key)
    if existing is not None:
        return existing, False

    timestamp = _as_utc(now or datetime.now(UTC))
    job = AccountEmailJob(
        user_id=user.id if user is not None else None,
        organization_id=user.organization_id if user is not None else None,
        kind=kind,
        status=AccountEmailStatus.PENDING,
        active_key=active_key,
        idempotency_key=f"account-email:{uuid4()}",
        attempt_count=0,
        next_attempt_at=timestamp,
        scheduled_at=timestamp,
        updated_at=timestamp,
    )
    try:
        async with session.begin_nested():
            session.add(job)
            await session.flush()
    except IntegrityError:
        existing = await _active_job(session, kind=kind, active_key=active_key)
        if existing is None:
            raise
        return existing, False
    return job, True


async def _active_job(
    session: AsyncSession,
    *,
    kind: AccountEmailKind,
    active_key: str,
) -> AccountEmailJob | None:
    return (
        await session.execute(
            select(AccountEmailJob).where(
                AccountEmailJob.kind == kind,
                AccountEmailJob.active_key == active_key,
            )
        )
    ).scalar_one_or_none()


async def prune_account_email_jobs(
    session: AsyncSession,
    *,
    older_than_days: int,
    now: datetime | None = None,
) -> int:
    """Delete only terminal jobs beyond their operational retention window.

    Anonymous no-account requests contain no address or payload and are removed
    after one day to cap distributed storage abuse. Jobs tied to a real account
    retain their status for the configured period. Pending and leased work is
    never eligible.
    """
    timestamp = _as_utc(now or datetime.now(UTC))
    terminal_cutoff = timestamp - timedelta(days=max(older_than_days, 1))
    anonymous_cutoff = timestamp - _ANONYMOUS_CANCEL_RETENTION
    terminal = AccountEmailJob.status.in_(
        (
            AccountEmailStatus.SENT,
            AccountEmailStatus.FAILED,
            AccountEmailStatus.CANCELLED,
        )
    )
    expired = or_(
        and_(terminal, AccountEmailJob.finished_at < terminal_cutoff),
        and_(
            AccountEmailJob.status == AccountEmailStatus.CANCELLED,
            AccountEmailJob.user_id.is_(None),
            AccountEmailJob.finished_at < anonymous_cutoff,
        ),
    )
    removed = (
        await session.execute(
            delete(AccountEmailJob)
            .where(AccountEmailJob.finished_at.is_not(None), expired)
            .returning(AccountEmailJob.id)
        )
    ).scalars()
    return len(list(removed))


class AccountEmailWorker:
    """Lease and deliver a bounded batch of account email jobs."""

    def __init__(
        self,
        db: Database,
        settings: Settings,
        *,
        channel: EmailChannel | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._channel_override = channel
        self._box = SecretBox(*settings.encryption_keys)

    async def drain(
        self,
        *,
        limit: int = 50,
        now: datetime | None = None,
        lease_seconds: int = _LEASE_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> int:
        """Process at most ``limit`` due jobs; return finalized attempt count."""
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        if now is not None and clock is not None:
            raise ValueError("Use either a frozen now or a current clock")
        current_time = clock or (lambda: now or datetime.now(UTC))
        if limit < 1:
            return 0
        attempted = 0
        finalized_count = 0
        while attempted < limit:
            attempt_time = _as_utc(current_time())
            async with self._db.session() as session:
                claimed = await _claim_next(
                    session,
                    now=attempt_time,
                    lease_seconds=lease_seconds,
                )
            if claimed is None:
                break
            attempted += 1

            remaining = (claimed.lease_expires_at - _as_utc(current_time())).total_seconds()
            if remaining <= 0:
                logger.warning("account email lease expired before delivery of job %s", claimed.id)
                continue
            try:
                # Includes identity/settings lookup and rendering, not just the
                # provider call. Leave room to persist the outcome while owned.
                result = await asyncio.wait_for(
                    self._deliver(claimed, issued_at=attempt_time), timeout=remaining * 0.9
                )
            except TimeoutError:
                result = _retryable(expires_at=None, error_code="delivery_timeout")
            finished_at = _as_utc(current_time())
            async with self._db.session() as session:
                finalized = await _finish(
                    session,
                    claimed,
                    result,
                    now=finished_at,
                )
            if finalized:
                finalized_count += 1
            else:
                logger.warning("account email lease lost before job %s was finalized", claimed.id)
        return finalized_count

    async def _deliver(
        self,
        claimed: ClaimedAccountEmail,
        *,
        issued_at: datetime,
    ) -> _DeliveryResult:
        if claimed.user_id is None:
            return _cancelled("recipient_unavailable")

        expires_at: datetime | None = None
        try:
            async with self._db.session() as session:
                user = await session.get(User, claimed.user_id)
                if (
                    user is None
                    or not user.is_active
                    or user.organization_id != claimed.organization_id
                ):
                    return _cancelled("recipient_unavailable")
                store = SettingsStore(session, self._box, org_id=claimed.organization_id)
                config = await store.email(
                    default_from=default_sender_email(self._settings.base_url)
                )
                brand_name = await store.brand_name()
                language = await store.email_language()
                log_only_delivery = isinstance(self._channel_override, LogChannel) or (
                    self._channel_override is None and config.channel is EmailChannelName.LOG
                )
                if log_only_delivery:
                    logger.warning(
                        "account email delivery unavailable: job=%s kind=%s "
                        "error_code=email_not_configured",
                        claimed.id,
                        claimed.kind.value,
                    )
                    return _retryable(
                        expires_at=None,
                        error_code="email_not_configured",
                    )
                envelope, expires_at = _render_envelope(
                    claimed,
                    user,
                    settings=self._settings,
                    issued_at=issued_at,
                    brand_name=brand_name,
                    language=language,
                )
            channel = self._channel_override or build_channel(config)
            message_id = await channel.send(envelope)
        except EmailConfigurationError as exc:
            _log_delivery_failure(claimed, exc)
            return _retryable(expires_at=expires_at, error_code="email_not_configured")
        except SendError as exc:
            _log_delivery_failure(claimed, exc)
            return _retryable(expires_at=expires_at, error_code="delivery_failed")
        except Exception as exc:
            # Never render the exception: provider errors may echo the address,
            # submitted body, or reset link.
            _log_delivery_failure(claimed, exc)
            return _retryable(expires_at=expires_at, error_code="delivery_failed")

        return _DeliveryResult(
            state="sent",
            token_expires_at=expires_at,
            provider_message_id=_bounded_message_id(message_id),
        )


async def _claim_next(
    session: AsyncSession,
    *,
    now: datetime,
    lease_seconds: int,
) -> ClaimedAccountEmail | None:
    lease_available = or_(
        AccountEmailJob.lease_token.is_(None),
        AccountEmailJob.lease_expires_at.is_(None),
        AccountEmailJob.lease_expires_at <= now,
    )
    due = and_(
        AccountEmailJob.status == AccountEmailStatus.PENDING,
        or_(
            AccountEmailJob.next_attempt_at.is_(None),
            AccountEmailJob.next_attempt_at <= now,
        ),
    )
    # Hard crashes never reach _finish. Exhaustion must therefore be enforced
    # when the last claim becomes reclaimable, without touching a live owner.
    await session.execute(
        update(AccountEmailJob)
        # Let SQL determine matches. SQLite reloads datetime values without
        # tzinfo, so Python-side ORM predicate evaluation is unsafe here.
        .execution_options(synchronize_session="fetch")
        .where(due, lease_available, AccountEmailJob.attempt_count >= _MAX_ATTEMPTS)
        .values(
            status=AccountEmailStatus.FAILED,
            active_key=None,
            lease_token=None,
            lease_expires_at=None,
            next_attempt_at=None,
            last_error_code="attempt_budget_exhausted",
            finished_at=now,
            updated_at=now,
        )
    )
    budget_available = AccountEmailJob.attempt_count < _MAX_ATTEMPTS
    candidate = (
        select(AccountEmailJob.id)
        .where(due, lease_available, budget_available)
        .order_by(AccountEmailJob.next_attempt_at.asc().nulls_first(), AccountEmailJob.id.asc())
        .limit(1)
        .scalar_subquery()
    )
    token = str(uuid4())
    expires_at = now + timedelta(seconds=lease_seconds)
    claimed = (
        await session.execute(
            update(AccountEmailJob)
            .execution_options(synchronize_session="fetch")
            .where(AccountEmailJob.id == candidate, due, lease_available, budget_available)
            .values(
                lease_token=token,
                lease_expires_at=expires_at,
                attempt_count=AccountEmailJob.attempt_count + 1,
                updated_at=now,
            )
            .returning(
                AccountEmailJob.id,
                AccountEmailJob.user_id,
                AccountEmailJob.organization_id,
                AccountEmailJob.kind,
                AccountEmailJob.idempotency_key,
                AccountEmailJob.attempt_count,
            )
        )
    ).one_or_none()
    await session.commit()
    if claimed is None:
        return None
    return ClaimedAccountEmail(
        id=claimed.id,
        user_id=claimed.user_id,
        organization_id=claimed.organization_id,
        kind=AccountEmailKind(claimed.kind),
        idempotency_key=claimed.idempotency_key,
        attempt_count=claimed.attempt_count,
        lease_token=token,
        lease_expires_at=expires_at,
    )


async def _finish(
    session: AsyncSession,
    claimed: ClaimedAccountEmail,
    result: _DeliveryResult,
    *,
    now: datetime,
) -> bool:
    values: dict[str, object | None] = {
        "lease_token": None,
        "lease_expires_at": None,
        "updated_at": now,
        "token_expires_at": result.token_expires_at,
    }
    if result.state == "sent":
        values.update(
            status=AccountEmailStatus.SENT,
            active_key=None,
            next_attempt_at=None,
            last_error_code=None,
            provider_message_id=result.provider_message_id,
            delivered_at=now,
            finished_at=now,
        )
    elif result.state == "cancelled":
        values.update(
            status=AccountEmailStatus.CANCELLED,
            active_key=None,
            next_attempt_at=None,
            last_error_code=result.error_code,
            finished_at=now,
        )
    elif claimed.attempt_count >= _MAX_ATTEMPTS:
        values.update(
            status=AccountEmailStatus.FAILED,
            active_key=None,
            next_attempt_at=None,
            last_error_code=result.error_code or "delivery_failed",
            finished_at=now,
        )
    else:
        values.update(
            status=AccountEmailStatus.PENDING,
            next_attempt_at=now + _retry_delay(claimed.attempt_count),
            last_error_code=result.error_code or "delivery_failed",
        )

    changed = (
        await session.execute(
            update(AccountEmailJob)
            .execution_options(synchronize_session="fetch")
            .where(
                AccountEmailJob.id == claimed.id,
                AccountEmailJob.status == AccountEmailStatus.PENDING,
                AccountEmailJob.lease_token == claimed.lease_token,
                AccountEmailJob.lease_expires_at > now,
            )
            .values(**values)
            .returning(AccountEmailJob.id)
        )
    ).scalar_one_or_none()
    await session.commit()
    return changed is not None


def _render_envelope(
    claimed: ClaimedAccountEmail,
    user: User,
    *,
    settings: Settings,
    issued_at: datetime,
    brand_name: str,
    language: str,
) -> tuple[EmailEnvelope, datetime]:
    ttl_seconds = (
        PASSWORD_RESET_TTL_SECONDS
        if claimed.kind is AccountEmailKind.PASSWORD_RESET
        else ACCOUNT_INVITATION_TTL_SECONDS
    )
    token = issue_scoped_token(
        user.id,
        secret=settings.token_secret,
        purpose=PURPOSE_PASSWORD_RESET,
        ttl_seconds=ttl_seconds,
        token_version=user.token_version,
        session_generation=user.session_generation,
        issued_at=issued_at,
    )
    target_url = f"{settings.base_url.rstrip('/')}/reset-password#token={token}"
    if claimed.kind is AccountEmailKind.PASSWORD_RESET:
        message = render_password_reset_email(
            reset_url=target_url,
            valid_minutes=ttl_seconds // 60,
            brand_name=brand_name,
            language=language,
        )
    else:
        message = render_account_invite_email(
            setup_url=target_url,
            valid_hours=ttl_seconds // 3600,
            brand_name=brand_name,
            language=language,
        )
    return (
        EmailEnvelope(
            to=user.email,
            to_name=user.name,
            subject=message.subject,
            html_body=message.html_body,
            text_body=message.text_body,
            idempotency_key=claimed.idempotency_key,
        ),
        issued_at + timedelta(seconds=ttl_seconds),
    )


def _address_key(secret: str, *, kind: AccountEmailKind, email: str) -> str:
    payload = f"account-email:v1:{kind.value}:{email.strip().lower()}".encode()
    return hmac.new(secret.encode(), payload, sha256).hexdigest()


def _retry_delay(attempt_count: int) -> timedelta:
    return _RETRY_BACKOFF[min(max(attempt_count - 1, 0), len(_RETRY_BACKOFF) - 1)]


def _cancelled(error_code: str) -> _DeliveryResult:
    return _DeliveryResult(
        state="cancelled",
        error_code=error_code,
    )


def _retryable(
    *,
    expires_at: datetime | None,
    error_code: str,
) -> _DeliveryResult:
    return _DeliveryResult(
        state="retry",
        token_expires_at=expires_at,
        error_code=error_code,
    )


def _bounded_message_id(message_id: str) -> str:
    return message_id.replace("\r", " ").replace("\n", " ")[:255]


def _log_delivery_failure(claimed: ClaimedAccountEmail, exc: Exception) -> None:
    logger.warning(
        "account email delivery failed: job=%s kind=%s error_type=%s",
        claimed.id,
        claimed.kind.value,
        type(exc).__name__,
    )


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
