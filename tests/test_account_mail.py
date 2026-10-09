"""Durable, replay-safe account email delivery."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import jwt
from sqlalchemy import select

from driftwatch.account_mail import AccountEmailWorker, prune_account_email_jobs
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.enums import AccountEmailKind, AccountEmailStatus, EmailChannelName
from driftwatch.models import AccountEmailJob, OrgSetting, User
from driftwatch.notifications.email import EmailEnvelope, LogChannel, SendError
from driftwatch.security.tokens import PURPOSE_PASSWORD_RESET, read_scoped_token


class ScriptedAccountChannel:
    name = EmailChannelName.BREVO

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.attempts: list[EmailEnvelope] = []

    async def send(self, envelope: EmailEnvelope) -> str:
        self.attempts.append(envelope)
        if self.fail:
            # Deliberately hostile provider error: the worker must never render
            # this exception into logs or durable status.
            raise SendError(f"provider echoed {envelope.to} {envelope.text_body}")
        return f"provider-{len(self.attempts)}"


async def _register(client: httpx.AsyncClient, email: str) -> int:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 201, response.text
    client.cookies.clear()
    return int(response.json()["id"])


async def _request_reset(client: httpx.AsyncClient, email: str) -> None:
    response = await client.post("/api/auth/request-password-reset", json={"email": email})
    assert response.status_code == 204, response.text


def _token(envelope: EmailEnvelope) -> str:
    match = re.search(r"/reset-password#token=([^\s]+)", envelope.text_body)
    assert match is not None
    return match.group(1)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def test_worker_resolves_current_identity_and_tenant_settings_at_delivery(
    client: httpx.AsyncClient,
    database: Database,
    settings: Settings,
) -> None:
    user_id = await _register(client, "current@example.com")
    await _request_reset(client, "current@example.com")
    generation = str(uuid4())

    async with database.session() as session:
        user = await session.get(User, user_id)
        assert user is not None and user.organization_id is not None
        user.token_version = 7
        user.session_generation = generation
        session.add_all(
            [
                OrgSetting(
                    organization_id=user.organization_id,
                    key="brand_name",
                    value="Current Brand",
                ),
                OrgSetting(
                    organization_id=user.organization_id,
                    key="email_language",
                    value="pl",
                ),
            ]
        )
        await session.commit()

    channel = ScriptedAccountChannel()
    issued_at = datetime.now(UTC)
    worker = AccountEmailWorker(database, settings, channel=channel)
    assert await worker.drain(now=issued_at) == 1
    assert len(channel.attempts) == 1
    assert "Current Brand" in channel.attempts[0].subject

    token = _token(channel.attempts[0])
    claims = read_scoped_token(
        token,
        secret=settings.token_secrets,
        purpose=PURPOSE_PASSWORD_RESET,
    )
    raw = jwt.decode(
        token,
        settings.token_secret,
        algorithms=["HS256"],
        options={"verify_exp": False},
    )
    assert claims.token_version == 7
    assert claims.session_generation == generation
    assert raw["iat"] == int(issued_at.timestamp())
    assert raw["exp"] - raw["iat"] == 30 * 60

    async with database.session() as session:
        job = (await session.execute(select(AccountEmailJob))).scalar_one()
        assert job.status == AccountEmailStatus.SENT
        assert job.attempt_count == 1
        assert job.active_key is None
        assert job.provider_message_id == "provider-1"
        assert job.token_expires_at is not None
        assert _utc(job.token_expires_at) == issued_at + timedelta(minutes=30)
        persisted = str(job.__dict__)
        assert "current@example.com" not in persisted
        assert token not in persisted


async def test_failure_is_redacted_and_retried_with_stable_idempotency_key(
    client: httpx.AsyncClient,
    database: Database,
    settings: Settings,
    caplog,
) -> None:
    await _register(client, "private@example.com")
    await _request_reset(client, "private@example.com")
    channel = ScriptedAccountChannel(fail=True)
    worker = AccountEmailWorker(database, settings, channel=channel)
    started = datetime.now(UTC)

    with caplog.at_level(logging.WARNING, logger="driftwatch.account_mail"):
        assert await worker.drain(now=started) == 1

    first_token = _token(channel.attempts[0])
    rendered_log = caplog.text
    assert "error_type=SendError" in rendered_log
    assert "private@example.com" not in rendered_log
    assert first_token not in rendered_log

    async with database.session() as session:
        job = (await session.execute(select(AccountEmailJob))).scalar_one()
        first_key = job.idempotency_key
        assert job.status == AccountEmailStatus.PENDING
        assert job.attempt_count == 1
        assert job.last_error_code == "delivery_failed"
        assert job.next_attempt_at is not None
        assert _utc(job.next_attempt_at) == started + timedelta(minutes=1)
        assert first_token not in str(job.__dict__)

    assert await worker.drain(now=started + timedelta(seconds=59)) == 0
    channel.fail = False
    assert await worker.drain(now=started + timedelta(minutes=1)) == 1
    assert len(channel.attempts) == 2
    assert channel.attempts[0].idempotency_key == first_key
    assert channel.attempts[1].idempotency_key == first_key

    # Either provider attempt may have crossed the external side-effect boundary,
    # but consuming one token invalidates every sibling link for this generation.
    accepted = await client.post(
        "/api/auth/reset-password",
        json={"token": first_token, "new_password": "rotated-password"},
    )
    replay = await client.post(
        "/api/auth/reset-password",
        json={"token": _token(channel.attempts[1]), "new_password": "replay-password"},
    )
    assert accepted.status_code == 204
    assert replay.status_code == 400


async def test_delivery_retries_are_bounded(
    client: httpx.AsyncClient,
    database: Database,
    settings: Settings,
) -> None:
    await _register(client, "outage@example.com")
    await _request_reset(client, "outage@example.com")
    channel = ScriptedAccountChannel(fail=True)
    worker = AccountEmailWorker(database, settings, channel=channel)
    started = datetime.now(UTC)

    for offset in (0, 1, 6, 21, 81):
        assert await worker.drain(now=started + timedelta(minutes=offset)) == 1

    assert await worker.drain(now=started + timedelta(days=1)) == 0
    async with database.session() as session:
        job = (await session.execute(select(AccountEmailJob))).scalar_one()
        assert job.status == AccountEmailStatus.FAILED
        assert job.attempt_count == 5
        assert job.active_key is None
        assert job.next_attempt_at is None
        assert job.finished_at is not None
        assert job.last_error_code == "delivery_failed"


async def test_unconfigured_account_email_fails_closed(
    client: httpx.AsyncClient,
    database: Database,
    settings: Settings,
    caplog,
) -> None:
    await _register(client, "unconfigured@example.com")
    await _request_reset(client, "unconfigured@example.com")
    worker = AccountEmailWorker(database, settings)
    explicit_log_worker = AccountEmailWorker(database, settings, channel=LogChannel())
    started = datetime.now(UTC)

    with caplog.at_level(logging.WARNING, logger="driftwatch.account_mail"):
        for index, offset in enumerate((0, 1, 6, 21, 81)):
            current_worker = explicit_log_worker if index == 1 else worker
            assert await current_worker.drain(now=started + timedelta(minutes=offset)) == 1

    assert "error_code=email_not_configured" in caplog.text
    assert "unconfigured@example.com" not in caplog.text
    assert "#token=" not in caplog.text
    async with database.session() as session:
        job = (await session.execute(select(AccountEmailJob))).scalar_one()
        assert job.status == AccountEmailStatus.FAILED
        assert job.attempt_count == 5
        assert job.last_error_code == "email_not_configured"
        assert job.token_expires_at is None
        assert job.provider_message_id is None


async def test_expired_lease_is_recovered(
    client: httpx.AsyncClient,
    database: Database,
    settings: Settings,
) -> None:
    await _register(client, "leased@example.com")
    await _request_reset(client, "leased@example.com")
    started = datetime.now(UTC)
    async with database.session() as session:
        job = (await session.execute(select(AccountEmailJob))).scalar_one()
        job.lease_token = "abandoned-worker"
        job.lease_expires_at = started + timedelta(seconds=30)
        await session.commit()

    channel = ScriptedAccountChannel()
    worker = AccountEmailWorker(database, settings, channel=channel)
    assert await worker.drain(now=started) == 0
    assert await worker.drain(now=started + timedelta(seconds=31)) == 1
    assert len(channel.attempts) == 1


async def test_prune_removes_only_expired_terminal_jobs(
    client: httpx.AsyncClient,
    database: Database,
) -> None:
    user_id = await _register(client, "retention@example.com")
    now = datetime.now(UTC)

    def job(
        suffix: str,
        status: AccountEmailStatus,
        *,
        age: timedelta,
        anonymous: bool = False,
        active_key: str | None = None,
        lease_token: str | None = None,
    ) -> AccountEmailJob:
        timestamp = now - age
        terminal = status is not AccountEmailStatus.PENDING
        return AccountEmailJob(
            user_id=None if anonymous else user_id,
            kind=AccountEmailKind.PASSWORD_RESET,
            status=status,
            active_key=active_key,
            idempotency_key=f"account-email:retention:{suffix}",
            attempt_count=1,
            next_attempt_at=None if terminal else timestamp,
            lease_token=lease_token,
            lease_expires_at=now + timedelta(minutes=1) if lease_token else None,
            scheduled_at=timestamp,
            finished_at=timestamp if terminal else None,
            updated_at=timestamp,
        )

    async with database.session() as session:
        rows = [
            job("old-sent", AccountEmailStatus.SENT, age=timedelta(days=31)),
            job("old-failed", AccountEmailStatus.FAILED, age=timedelta(days=31)),
            job("old-cancelled", AccountEmailStatus.CANCELLED, age=timedelta(days=31)),
            job(
                "anonymous-cancelled",
                AccountEmailStatus.CANCELLED,
                age=timedelta(days=2),
                anonymous=True,
            ),
            job("recent-failed", AccountEmailStatus.FAILED, age=timedelta(hours=2)),
            job(
                "old-pending",
                AccountEmailStatus.PENDING,
                age=timedelta(days=90),
                active_key="b" * 64,
            ),
            job(
                "old-leased",
                AccountEmailStatus.PENDING,
                age=timedelta(days=90),
                active_key="c" * 64,
                lease_token="active-worker",
            ),
        ]
        session.add_all(rows)
        await session.flush()
        expected_remaining = {row.id for row in rows[4:]}
        assert await prune_account_email_jobs(session, older_than_days=30, now=now) == 4
        await session.commit()

    async with database.session() as session:
        remaining = set((await session.execute(select(AccountEmailJob.id))).scalars())
    assert remaining == expected_remaining
