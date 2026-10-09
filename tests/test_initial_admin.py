"""Fresh self-hosted ownership is atomic, persistent, and fail-closed."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import Message, Receive, Scope, Send

import driftwatch.api.auth as auth_api
from conftest import FakePicker, RecordingChannel, ScriptedCapturer, StubAnalyzer
from driftwatch.app import create_app
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.models import InstanceBootstrap, Organization, User
from driftwatch.security import two_factor
from driftwatch.seed import seed_admin

_PASSWORD = "owned-test-password-123"


@asynccontextmanager
async def _installation(settings: Settings) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(
        settings,
        capturer=ScriptedCapturer(html="<main>Owned observation</main>"),
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
        yield client, app


def _fresh_settings(settings: Settings, **overrides: object) -> Settings:
    return settings.model_copy(
        update={
            "public_registration_enabled": False,
            "initial_admin_email": None,
            "initial_admin_password": None,
            **overrides,
        }
    )


async def _register(client: httpx.AsyncClient, email: str, **fields: object) -> httpx.Response:
    return await client.post(
        "/api/auth/register", json={"email": email, "password": _PASSWORD, **fields}
    )


async def test_fresh_owner_claim_closes_registration_and_names_home_workspace(
    settings: Settings,
) -> None:
    async with _installation(_fresh_settings(settings)) as (client, app):
        available = await client.get("/api/auth/capabilities")
        assert available.headers["cache-control"] == "no-store"
        assert available.json() == {
            "registration_enabled": True,
            "initial_setup_required": True,
        }
        owner = await _register(client, "owner@example.com", organization_name="My workspace")
        assert owner.status_code == 201, owner.text
        assert owner.json()["is_admin"] is True
        assert owner.json()["is_superadmin"] is True
        assert (await client.get("/api/auth/me")).json()["id"] == owner.json()["id"]
        assert (await client.get("/api/auth/capabilities")).json() == {
            "registration_enabled": False,
            "initial_setup_required": False,
        }
        second = await _register(client, "second@example.com", is_superadmin=True, is_admin=True)
        assert second.status_code == 403
        async with app.state.db.session() as session:
            assert (await session.scalar(select(Organization))).name == "My workspace"
            assert (await session.get(InstanceBootstrap, 1)).completed is True
            assert await session.scalar(select(func.count(User.id))) == 1


async def test_explicit_open_registration_never_takes_roles_from_payload(
    settings: Settings,
) -> None:
    configured = _fresh_settings(settings, public_registration_enabled=True)
    async with _installation(configured) as (client, _):
        assert (await _register(client, "owner@example.com")).status_code == 201
        member = await _register(client, "member@example.com", is_superadmin=True, is_admin=True)
        assert member.status_code == 201, member.text
        assert member.json()["is_superadmin"] is False
        assert member.json()["is_admin"] is False


async def test_parallel_first_registrations_create_exactly_one_owner(settings: Settings) -> None:
    async with _installation(_fresh_settings(settings)) as (_, app):
        start = asyncio.Event()

        async def attempt(index: int) -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=settings.base_url
            ) as client:
                await start.wait()
                return await _register(client, f"owner-{index}@example.com")

        attempts = [asyncio.create_task(attempt(index)) for index in range(8)]
        start.set()
        results = await asyncio.gather(*attempts)
        assert sorted(result.status_code for result in results) == [201, *([403] * 7)]
        async with app.state.db.session() as session:
            users = list(await session.scalars(select(User)))
            assert len(users) == 1
            assert users[0].is_superadmin is True
            assert await session.scalar(select(func.count(Organization.id))) == 1


async def test_failed_registration_rolls_back_claim_and_workspace(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = _fresh_settings(settings)
    original_hash = auth_api.ahash_password

    async def failed_hash(_: str) -> str:
        raise RuntimeError("isolated failure before account persistence")

    async with _installation(configured) as (client, app):
        monkeypatch.setattr(auth_api, "ahash_password", failed_hash)
        with pytest.raises(RuntimeError, match="isolated failure"):
            await _register(client, "failed@example.com")
        async with app.state.db.session() as session:
            assert (await session.get(InstanceBootstrap, 1)).completed is False
            assert await session.scalar(select(func.count(Organization.id))) == 0
        monkeypatch.setattr(auth_api, "ahash_password", original_hash)
        assert (await _register(client, "owner@example.com")).status_code == 201


async def test_registration_commits_before_success_and_commit_failure_releases_claim(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = _fresh_settings(settings)
    original_commit = AsyncSession.commit
    commit_attempts = 0
    responses: list[tuple[int, int, bool]] = []

    async def fail_first_commit(session: AsyncSession) -> None:
        nonlocal commit_attempts
        commit_attempts += 1
        if commit_attempts == 1:
            raise RuntimeError("isolated database commit failure")
        await original_commit(session)

    async with _installation(configured) as (_, app):
        monkeypatch.setattr(AsyncSession, "commit", fail_first_commit)

        async def observed_app(scope: Scope, receive: Receive, send: Send) -> None:
            async def observe_send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    async with app.state.db.session() as probe:
                        count = await probe.scalar(select(func.count(User.id)))
                        completed = (await probe.get(InstanceBootstrap, 1)).completed
                    responses.append((message["status"], count, completed))
                await send(message)

            await app(scope, receive, observe_send)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=observed_app, raise_app_exceptions=False),
            base_url=configured.base_url,
        ) as client:
            failed = await _register(client, "owner@example.com")
            assert failed.status_code == 500, failed.text
            assert "set-cookie" not in failed.headers
            assert responses == [(500, 0, False)]
            retry = await _register(client, "owner@example.com")
            assert retry.status_code == 201, retry.text
            assert "set-cookie" in retry.headers
            assert responses == [(500, 0, False), (201, 1, True)]
            # Signup owns its commit; no late cleanup commit can revoke a 201.
            assert commit_attempts == 2


async def test_first_owner_mfa_is_durable_before_session_and_recovery_codes(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = _fresh_settings(
        settings,
        host="0.0.0.0",
        base_url="https://driftwatch.example.test",
        session_secret_key="first-owner-session-domain-0123456789-abcd",
        encryption_key="first-owner-encryption-domain-0123456789-abcd",
        initial_admin_signup_enabled=True,
    )
    original_commit = AsyncSession.commit
    commit_attempts = 0
    responses: list[tuple[int, bool, int]] = []

    async def fail_first_commit(session: AsyncSession) -> None:
        nonlocal commit_attempts
        commit_attempts += 1
        if commit_attempts == 1:
            raise RuntimeError("isolated MFA commit failure")
        await original_commit(session)

    async with _installation(configured) as (client, app):
        owner = (await _register(client, "owner@example.com")).json()
        headers = {"X-Acting-Org": str(owner["organization_id"])}
        await client.post("/api/auth/step-up", headers=headers, json={"password": _PASSWORD})
        setup = await client.post("/api/auth/totp/setup", headers=headers)
        assert setup.status_code == 200
        secret = setup.json()["secret"]
        old_session = client.cookies.get("driftwatch_session")
        async with app.state.db.session() as probe:
            previous_version = (await probe.get(User, owner["id"])).token_version
        monkeypatch.setattr(AsyncSession, "commit", fail_first_commit)

        async def observed_app(scope: Scope, receive: Receive, send: Send) -> None:
            async def observe_send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    async with app.state.db.session() as probe:
                        persisted = await probe.get(User, owner["id"])
                        responses.append(
                            (message["status"], persisted.totp_enabled, persisted.token_version)
                        )
                await send(message)

            await app(scope, receive, observe_send)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=observed_app, raise_app_exceptions=False),
            base_url=configured.base_url,
            cookies=client.cookies,
        ) as enrollment:
            payload = {"code": two_factor.generate_code(secret)}
            failed = await enrollment.post("/api/auth/totp/enable", headers=headers, json=payload)
            assert failed.status_code == 500
            assert "set-cookie" not in failed.headers
            assert responses == [(500, False, previous_version)]
            assert commit_attempts == 1
            assert (await client.get("/api/auth/me", headers=headers)).status_code == 200
            # The ordinary read dependency commits its own session cleanup.
            assert commit_attempts == 2
            retry = await enrollment.post("/api/auth/totp/enable", headers=headers, json=payload)
            assert retry.status_code == 200, retry.text
            assert len(retry.json()["recovery_codes"]) == 10
            assert responses[-1] == (200, True, previous_version + 1)
            assert commit_attempts == 3
            assert enrollment.cookies.get("driftwatch_session") != old_session
            assert (await enrollment.get("/api/auth/me", headers=headers)).status_code == 200
            assert (await client.get("/api/auth/me", headers=headers)).status_code == 401


async def test_restart_and_removing_all_accounts_cannot_reopen_claim(settings: Settings) -> None:
    configured = _fresh_settings(settings)
    async with _installation(configured) as (client, app):
        assert (await _register(client, "owner@example.com")).status_code == 201
        async with app.state.db.session() as session:
            await session.execute(delete(User))
            await session.execute(delete(Organization))
            await session.commit()
    configured = configured.model_copy(
        update={
            "initial_admin_email": "unexpected-reseed@example.com",
            "initial_admin_password": _PASSWORD,
        }
    )
    async with _installation(configured) as (client, app):
        assert (await client.get("/api/auth/capabilities")).json() == {
            "registration_enabled": False,
            "initial_setup_required": False,
        }
        assert (await _register(client, "replacement@example.com")).status_code == 403
        async with app.state.db.session() as session:
            assert (await session.get(InstanceBootstrap, 1)).completed is True
            assert await session.scalar(select(func.count(User.id))) == 0


async def test_parallel_startup_seeds_use_the_same_single_claim(
    database: Database, settings: Settings
) -> None:
    configurations = [
        _fresh_settings(
            settings,
            initial_admin_email=f"seed-{index}@example.com",
            initial_admin_password=_PASSWORD,
        )
        for index in range(6)
    ]
    await asyncio.gather(*(seed_admin(database, configured) for configured in configurations))
    async with database.session() as session:
        users = list(await session.scalars(select(User)))
        assert len(users) == 1
        assert users[0].is_superadmin is True
        assert (await session.get(InstanceBootstrap, 1)).completed is True


async def test_seed_and_browser_registration_compete_for_one_claim(settings: Settings) -> None:
    configured = _fresh_settings(settings)
    seeded = configured.model_copy(
        update={
            "initial_admin_email": "seed@example.com",
            "initial_admin_password": _PASSWORD,
        }
    )
    async with _installation(configured) as (client, app):
        _, signup = await asyncio.gather(
            seed_admin(app.state.db, seeded), _register(client, "signup@example.com")
        )
        assert signup.status_code in {201, 403}, signup.text
        async with app.state.db.session() as session:
            users = list(await session.scalars(select(User)))
            assert len(users) == 1
            assert users[0].is_superadmin is True
            assert users[0].email in {"seed@example.com", "signup@example.com"}


async def test_explicitly_disabled_initial_claim_is_not_exposed(settings: Settings) -> None:
    configured = _fresh_settings(settings, initial_admin_signup_enabled=False)
    async with _installation(configured) as (client, _):
        assert (await client.get("/api/auth/capabilities")).json() == {
            "registration_enabled": False,
            "initial_setup_required": False,
        }
        assert (await _register(client, "unexpected@example.com")).status_code == 403


async def test_public_opt_in_owner_can_work_in_home_org_without_support_grant(
    settings: Settings,
) -> None:
    configured = _fresh_settings(
        settings,
        host="0.0.0.0",
        base_url="https://driftwatch.example.test",
        session_secret_key="first-owner-session-domain-0123456789-abcd",
        encryption_key="first-owner-encryption-domain-0123456789-abcd",
        initial_admin_signup_enabled=True,
    )
    async with _installation(configured) as (client, _):
        owner = await _register(client, "owner@example.com")
        assert owner.status_code == 201, owner.text
        assert owner.json()["is_superadmin"] is True
        assert owner.json()["mfa_enrollment_required"] is True
        home_headers = {"X-Acting-Org": str(owner.json()["organization_id"])}
        confirmed = await client.get("/api/auth/me", headers=home_headers)
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["acting_organization_id"] == owner.json()["organization_id"]
        assert confirmed.json()["mfa_enrollment_required"] is True
        assert (
            await client.post(
                "/api/sites", headers=home_headers, json={"url": "https://owned.example.test"}
            )
        ).status_code == 428
        assert (
            await client.post(
                "/api/auth/step-up", headers=home_headers, json={"password": _PASSWORD}
            )
        ).status_code == 204
        setup = await client.post("/api/auth/totp/setup", headers=home_headers)
        assert setup.status_code == 200, setup.text
        secret = setup.json()["secret"]
        assert (
            await client.post(
                "/api/auth/totp/enable",
                headers=home_headers,
                json={"code": two_factor.generate_code(secret)},
            )
        ).status_code == 200
        access = await client.get("/api/support-access", headers=home_headers)
        assert access.status_code == 200, access.text
        assert access.json()["required"] is False
        assert access.json()["access_enabled"] is True
        site = await client.post(
            "/api/sites", headers=home_headers, json={"url": "https://owned.example.test"}
        )
        assert site.status_code == 201, site.text
        baseline = await client.post(f"/api/sites/{site.json()['id']}/check", headers=home_headers)
        assert baseline.status_code == 200, baseline.text
        assert baseline.json()["status"] == "baseline"
        assert (
            await client.post(
                "/api/auth/step-up",
                json={"password": _PASSWORD, "totp_code": two_factor.generate_code(secret)},
            )
        ).status_code == 204
        other = await client.post("/api/organizations", json={"name": "Other workspace"})
        assert other.status_code == 201, other.text
        other_headers = {"X-Acting-Org": str(other.json()["id"])}
        denied = await client.get("/api/sites", headers=other_headers)
        assert denied.status_code == 403, denied.text
        assert (await client.get("/api/sites", headers=home_headers)).json()[0][
            "id"
        ] == site.json()["id"]
