"""HTTP success and credentials must describe committed database state.

Observe the real ASGI response headers with a separate database connection. A
client can act on those headers before the request task has finished, so merely
checking persistence after ``client.post`` would miss a late commit failure.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path as FilesystemPath

import httpx
import pytest
import pytest_asyncio
from anyio import Path
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import Message, Receive, Scope, Send

from conftest import FakePicker, RecordingChannel, ScriptedCapturer, StubAnalyzer
from driftwatch.api.deps import PENDING_TOTP_COOKIE, SESSION_COOKIE
from driftwatch.app import create_app
from driftwatch.config import Settings
from driftwatch.models import AuditEvent, Project, User
from driftwatch.security import two_factor
from driftwatch.security.passwords import averify_password
from driftwatch.security.tokens import read_pending_login

_EMAIL = "transaction-owner@example.com"
_PASSWORD = "owned-transaction-password-123"
_NEW_PASSWORD = "owned-new-transaction-password-456"
_Probe = Callable[[AsyncSession], Awaitable[object]]


@pytest.fixture
def settings(tmp_path: FilesystemPath) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        secret_key=secrets.token_urlsafe(48),
        scheduler_enabled=False,
        run_migrations=True,
        base_url="http://localhost:8000",
        public_registration_enabled=True,
        initial_admin_email=None,
        initial_admin_password=None,
    )


@pytest_asyncio.fixture
async def installation(settings: Settings) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient, int]]:
    app = create_app(
        settings,
        capturer=ScriptedCapturer(html="<main>Owned transaction fixture</main>"),
        analyzer=StubAnalyzer(),
        channel=RecordingChannel(),
        picker=FakePicker(),
        enable_scheduler=False,
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=settings.base_url
        ) as client,
    ):
        registered = await client.post(
            "/api/auth/register", json={"email": _EMAIL, "password": _PASSWORD}
        )
        assert registered.status_code == 201, registered.text
        yield app, client, registered.json()["id"]


@asynccontextmanager
async def _observe_headers(
    app: FastAPI, client: httpx.AsyncClient, probe: _Probe
) -> AsyncIterator[tuple[httpx.AsyncClient, list[tuple[int, object]]]]:
    observations: list[tuple[int, object]] = []

    async def observed_app(scope: Scope, receive: Receive, send: Send) -> None:
        async def observe_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                async with app.state.db.session() as session:
                    observations.append((message["status"], await probe(session)))
            await send(message)

        await app(scope, receive, observe_send)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=observed_app, raise_app_exceptions=False),
        base_url=client.base_url,
        cookies=client.cookies,
    ) as observed_client:
        yield observed_client, observations


def _fail_next_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    original_commit = AsyncSession.commit
    fail = True

    async def commit(session: AsyncSession) -> None:
        nonlocal fail
        if fail:
            fail = False
            raise RuntimeError("owned transaction-boundary commit failure")
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", commit)


async def _enable_totp(client: httpx.AsyncClient) -> tuple[str, list[str]]:
    assert (await client.post("/api/auth/step-up", json={"password": _PASSWORD})).status_code == 204
    setup = await client.post("/api/auth/totp/setup")
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    enabled = await client.post(
        "/api/auth/totp/enable", json={"code": two_factor.generate_code(secret)}
    )
    assert enabled.status_code == 200, enabled.text
    return secret, enabled.json()["recovery_codes"]


async def test_password_commit_failure_sends_no_success_or_new_session(
    installation: tuple[FastAPI, httpx.AsyncClient, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, client, user_id = installation
    old_token = client.cookies.get(SESSION_COOKIE)

    async def probe(session: AsyncSession) -> object:
        user = await session.get(User, user_id)
        assert user is not None
        return (
            await averify_password(_PASSWORD, user.password_hash),
            await averify_password(_NEW_PASSWORD, user.password_hash),
            user.token_version,
            await session.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.action == "account.password_changed"
                )
            ),
        )

    _fail_next_commit(monkeypatch)
    async with _observe_headers(app, client, probe) as (observed, headers):
        payload = {"current_password": _PASSWORD, "new_password": _NEW_PASSWORD}
        failed = await observed.post("/api/auth/change-password", json=payload)
        assert failed.status_code == 500
        assert "set-cookie" not in failed.headers
        assert headers == [(500, (True, False, 0, 0))]
        # A failed write leaves the existing browser credential usable.
        assert (await client.get("/api/auth/me")).status_code == 200
        retry = await observed.post("/api/auth/change-password", json=payload)
        assert retry.status_code == 204
        assert headers[-1] == (204, (False, True, 1, 1))
        assert (await observed.get("/api/auth/me")).status_code == 200
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=client.base_url,
            cookies={SESSION_COOKIE: old_token},
        ) as old_browser:
            assert (await old_browser.get("/api/auth/me")).status_code == 401


async def test_totp_setup_secret_is_persisted_before_it_is_shown(
    installation: tuple[FastAPI, httpx.AsyncClient, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, client, user_id = installation
    assert (await client.post("/api/auth/step-up", json={"password": _PASSWORD})).status_code == 204

    async def probe(session: AsyncSession) -> object:
        user = await session.get(User, user_id)
        assert user is not None
        return app.state.secret_box.decrypt(user.totp_secret) if user.totp_secret else None

    _fail_next_commit(monkeypatch)
    async with _observe_headers(app, client, probe) as (observed, headers):
        failed = await observed.post("/api/auth/totp/setup")
        assert failed.status_code == 500
        assert "set-cookie" not in failed.headers
        assert headers == [(500, None)]
        retry = await observed.post("/api/auth/totp/setup")
        assert retry.status_code == 200
        assert headers[-1] == (200, retry.json()["secret"])


async def test_pending_login_challenge_is_durable_before_cookie(
    installation: tuple[FastAPI, httpx.AsyncClient, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, client, user_id = installation
    await _enable_totp(client)
    assert (await client.post("/api/auth/logout")).status_code == 204

    async def probe(session: AsyncSession) -> object:
        user = await session.get(User, user_id)
        assert user is not None
        return user.pending_totp_nonce

    _fail_next_commit(monkeypatch)
    async with _observe_headers(app, client, probe) as (observed, headers):
        payload = {"email": _EMAIL, "password": _PASSWORD}
        failed = await observed.post("/api/auth/login", json=payload)
        assert failed.status_code == 500
        assert "set-cookie" not in failed.headers
        assert headers == [(500, None)]
        retry = await observed.post("/api/auth/login", json=payload)
        assert retry.status_code == 200
        assert retry.json()["totp_required"] is True
        claims = read_pending_login(
            observed.cookies.get(PENDING_TOTP_COOKIE), secret=app.state.settings.token_secrets
        )
        assert headers[-1] == (200, claims.nonce)
        assert claims.nonce is not None
        assert SESSION_COOKIE not in observed.cookies


@pytest.mark.parametrize("factor", ["totp", "recovery"])
async def test_login_factor_commit_failure_preserves_challenge_and_retry_is_single_use(
    installation: tuple[FastAPI, httpx.AsyncClient, int],
    monkeypatch: pytest.MonkeyPatch,
    factor: str,
) -> None:
    app, client, user_id = installation
    secret, recovery_codes = await _enable_totp(client)
    assert (await client.post("/api/auth/logout")).status_code == 204
    pending = await client.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    assert pending.status_code == 200
    pending_token = client.cookies.get(PENDING_TOTP_COOKIE)
    claims = read_pending_login(pending_token, secret=app.state.settings.token_secrets)

    async def probe(session: AsyncSession) -> object:
        user = await session.get(User, user_id)
        assert user is not None
        return (
            user.pending_totp_nonce,
            user.totp_last_login_counter,
            len(user.recovery_code_hashes),
            await session.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.action == "account.recovery_code_used"
                )
            ),
        )

    code = two_factor.generate_code(secret) if factor == "totp" else recovery_codes[0]
    _fail_next_commit(monkeypatch)
    async with _observe_headers(app, client, probe) as (observed, headers):
        failed = await observed.post("/api/auth/login/totp", json={"code": code})
        assert failed.status_code == 500
        assert "set-cookie" not in failed.headers
        assert headers == [(500, (claims.nonce, None, 10, 0))]
        retry = await observed.post("/api/auth/login/totp", json={"code": code})
        assert retry.status_code == 200
        expected_counter = two_factor.matching_counter(secret, code) if factor == "totp" else None
        assert headers[-1] == (
            200,
            (None, expected_counter, 10 if factor == "totp" else 9, 0 if factor == "totp" else 1),
        )
        assert PENDING_TOTP_COOKIE not in observed.cookies
        assert (await observed.get("/api/auth/me")).status_code == 200
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=client.base_url,
            cookies={PENDING_TOTP_COOKIE: pending_token},
        ) as replay:
            assert (
                await replay.post("/api/auth/login/totp", json={"code": code})
            ).status_code == 401
            # Even a fresh password challenge cannot reuse a spent login factor.
            assert (
                await replay.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
            ).status_code == 200
            assert (
                await replay.post("/api/auth/login/totp", json={"code": code})
            ).status_code == 401


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_project_mutation_is_durable_at_headers_and_rollback_can_be_retried(
    installation: tuple[FastAPI, httpx.AsyncClient, int],
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    app, client, _ = installation
    project_id = None
    if operation != "create":
        created = await client.post("/api/projects", json={"name": "Before mutation"})
        assert created.status_code == 201
        project_id = created.json()["id"]

    async def probe(session: AsyncSession) -> object:
        return list((await session.execute(select(Project.id, Project.name))).tuples())

    before = [] if project_id is None else [(project_id, "Before mutation")]
    method = {"create": "POST", "update": "PATCH", "delete": "DELETE"}[operation]
    path = "/api/projects" if operation == "create" else f"/api/projects/{project_id}"
    payload = {"name": "After mutation"} if operation != "delete" else None
    _fail_next_commit(monkeypatch)
    async with _observe_headers(app, client, probe) as (observed, headers):
        failed = await observed.request(method, path, json=payload)
        assert failed.status_code == 500
        assert headers == [(500, before)]
        retry = await observed.request(method, path, json=payload)
        success = {"create": 201, "update": 200, "delete": 204}[operation]
        assert retry.status_code == success, retry.text
        expected = [] if operation == "delete" else [(retry.json()["id"], "After mutation")]
        assert headers[-1] == (success, expected)
        if operation != "delete":
            assert retry.json()["name"] == "After mutation"


async def test_backup_failure_sends_no_file_and_removes_temporary_snapshot(
    installation: tuple[FastAPI, httpx.AsyncClient, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, client, _ = installation
    assert (await client.post("/api/auth/step-up", json={"password": _PASSWORD})).status_code == 204
    data_dir = Path(app.state.settings.data_dir)

    async def probe(session: AsyncSession) -> object:
        return await session.scalar(
            select(func.count(AuditEvent.id)).where(AuditEvent.action == "backup.downloaded")
        )

    _fail_next_commit(monkeypatch)
    async with _observe_headers(app, client, probe) as (observed, headers):
        failed = await observed.get("/api/admin/backup")
        assert failed.status_code == 500
        assert headers == [(500, 0)]
        assert not failed.content.startswith(b"SQLite format 3")
        assert [path async for path in data_dir.glob("driftwatch-backup-*.db")] == []
        retry = await observed.get("/api/admin/backup")
        assert retry.status_code == 200
        assert headers[-1] == (200, 1)
        assert retry.content.startswith(b"SQLite format 3")
        assert [path async for path in data_dir.glob("driftwatch-backup-*.db")] == []


async def test_cancelled_backup_removes_snapshot_without_recording_download(
    installation: tuple[FastAPI, httpx.AsyncClient, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, client, _ = installation
    assert (await client.post("/api/auth/step-up", json={"password": _PASSWORD})).status_code == 204
    original_commit = AsyncSession.commit

    async def cancelled_commit(_: AsyncSession) -> None:
        raise asyncio.CancelledError("owned backup cancellation")

    monkeypatch.setattr(AsyncSession, "commit", cancelled_commit)
    with pytest.raises(asyncio.CancelledError, match="owned backup cancellation"):
        await client.get("/api/admin/backup")
    data_dir = Path(app.state.settings.data_dir)
    assert [path async for path in data_dir.glob("driftwatch-backup-*.db")] == []
    async with app.state.db.session() as session:
        assert (
            await session.scalar(
                select(func.count(AuditEvent.id)).where(AuditEvent.action == "backup.downloaded")
            )
        ) == 0
    monkeypatch.setattr(AsyncSession, "commit", original_commit)
    assert (await client.get("/api/admin/backup")).status_code == 200
    assert [path async for path in data_dir.glob("driftwatch-backup-*.db")] == []
