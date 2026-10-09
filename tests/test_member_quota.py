"""Atomic member entitlements and account-creation abuse controls."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from sqlalchemy import func, select

from driftwatch.api.users import _USER_CREATION_LIMIT
from driftwatch.db import Database
from driftwatch.exceptions import PlanLimitReached
from driftwatch.models import AccountEmailJob, Organization, User
from driftwatch.quota import reserve_member_slot


async def _step_up(client: httpx.AsyncClient, organization_id: int | None = None) -> None:
    headers = {"X-Acting-Org": str(organization_id)} if organization_id is not None else None
    response = await client.post(
        "/api/auth/step-up",
        headers=headers,
        json={"password": "supersecret123"},
    )
    assert response.status_code == 204, response.text


async def _home_organization_id(client: httpx.AsyncClient) -> int:
    user = (await client.get("/api/auth/me")).json()
    assert user["organization_id"] is not None
    return int(user["organization_id"])


async def _tenant_counts(database: Database, organization_id: int) -> tuple[int, int, int]:
    async with database.session() as session:
        users = await session.scalar(
            select(func.count(User.id)).where(
                User.organization_id == organization_id,
                User.is_superadmin.is_(False),
            )
        )
        jobs = await session.scalar(
            select(func.count(AccountEmailJob.id)).where(
                AccountEmailJob.organization_id == organization_id
            )
        )
        organization = await session.get(Organization, organization_id)
        assert organization is not None
        return int(users or 0), int(jobs or 0), organization.member_slots_used


async def test_member_cap_rejects_without_creating_user_or_mail_job(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    organization_id = await _home_organization_id(admin_client)
    async with database.session() as session:
        organization = await session.get(Organization, organization_id)
        assert organization is not None
        organization.max_members = 1
        await session.commit()

    await _step_up(admin_client)
    first = await admin_client.post("/api/users", json={"email": "member-one@example.com"})
    assert first.status_code == 201, first.text
    organizations = (await admin_client.get("/api/organizations")).json()
    summary = next(item for item in organizations if item["id"] == organization_id)
    assert summary["member_count"] == 1  # the instance operator is not a tenant member
    before = await _tenant_counts(database, organization_id)

    rejected = await admin_client.post("/api/users", json={"email": "relay-target@example.com"})

    assert rejected.status_code == 403
    assert rejected.json()["detail"] == (
        "This workspace allows 1 member account(s). Contact an operator to request more access."
    )
    assert await _tenant_counts(database, organization_id) == before == (1, 1, 1)


async def test_deleting_member_releases_slot_in_the_same_transaction(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    organization_id = await _home_organization_id(admin_client)
    async with database.session() as session:
        organization = await session.get(Organization, organization_id)
        assert organization is not None
        organization.max_members = 1
        await session.commit()

    await _step_up(admin_client)
    created = await admin_client.post("/api/users", json={"email": "replace-me@example.com"})
    assert created.status_code == 201, created.text
    deleted = await admin_client.delete(f"/api/users/{created.json()['id']}")
    assert deleted.status_code == 204, deleted.text
    replacement = await admin_client.post("/api/users", json={"email": "replacement@example.com"})

    assert replacement.status_code == 201, replacement.text
    assert await _tenant_counts(database, organization_id) == (1, 1, 1)


async def test_user_create_throttle_is_shared_per_actor_and_organization(
    admin_client: httpx.AsyncClient,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fast_hash(_: str) -> str:
        return "test-only-unusable-hash"

    monkeypatch.setattr("driftwatch.api.users.ahash_password", fast_hash)
    organization_id = await _home_organization_id(admin_client)
    await _step_up(admin_client)

    for index in range(_USER_CREATION_LIMIT):
        response = await admin_client.post(
            "/api/users", json={"email": f"bulk-{index}@example.com"}
        )
        assert response.status_code == 201, response.text
    before = await _tenant_counts(database, organization_id)

    throttled = await admin_client.post("/api/users", json={"email": "bulk-refused@example.com"})
    assert throttled.status_code == 429
    assert int(throttled.headers["Retry-After"]) >= 1
    assert await _tenant_counts(database, organization_id) == before

    other = await admin_client.post("/api/organizations", json={"name": "Other throttle scope"})
    assert other.status_code == 201, other.text
    await _step_up(admin_client, int(other.json()["id"]))
    scoped = await admin_client.post(
        "/api/users",
        headers={"X-Acting-Org": str(other.json()["id"])},
        json={"email": "other-scope@example.com"},
    )
    assert scoped.status_code == 201, scoped.text


async def test_parallel_sqlite_member_reservations_cannot_exceed_cap(
    database: Database,
) -> None:
    async with database.session() as session:
        organization = Organization(name="Atomic members", max_members=2)
        session.add(organization)
        await session.commit()
        organization_id = organization.id

    async def create(index: int) -> bool:
        async with database.session() as session:
            try:
                await reserve_member_slot(session, organization_id)
            except PlanLimitReached:
                await session.rollback()
                return False
            session.add(
                User(
                    organization_id=organization_id,
                    email=f"sqlite-member-{index}@example.test",
                    password_hash="unusable-test-hash",
                )
            )
            await session.commit()
            return True

    results = await asyncio.gather(*(create(index) for index in range(4)))

    assert sum(results) == 2
    assert await _tenant_counts(database, organization_id) == (2, 0, 2)
