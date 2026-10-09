"""Concurrency and immutable-attribution regressions for tenant quotas."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from sqlalchemy import func, select
from tests.conftest import RecordingChannel, ScriptedCapturer, StubAnalyzer, create_org

from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.exceptions import AccessDenied, PlanLimitReached
from driftwatch.models import AIUsage, Organization, Site
from driftwatch.quota import (
    ai_check_limit_reached,
    release_site_slot,
    reserve_ai_check,
    reserve_site_slot,
)
from driftwatch.runner import SiteRunner


async def test_parallel_site_reservations_cannot_exceed_cap(database: Database) -> None:
    async with database.session() as session:
        org_id = await create_org(session, "Atomic sites")
        organization = await session.get(Organization, org_id)
        assert organization is not None
        organization.max_sites = 3
        await session.commit()

    async def create(index: int) -> bool:
        async with database.session() as session:
            try:
                await reserve_site_slot(session, org_id)
            except PlanLimitReached:
                await session.rollback()
                return False
            session.add(Site(organization_id=org_id, url=f"https://site-{index}.example"))
            await session.commit()
            return True

    results = await asyncio.gather(*(create(index) for index in range(12)))

    assert sum(results) == 3
    async with database.session() as session:
        count = (
            await session.execute(select(func.count(Site.id)).where(Site.organization_id == org_id))
        ).scalar_one()
        organization = await session.get(Organization, org_id)
        assert organization is not None
        assert count == organization.site_slots_used == 3


async def test_parallel_ai_reservations_cannot_exceed_monthly_cap(database: Database) -> None:
    async with database.session() as session:
        org_id = await create_org(session, "Atomic AI")
        organization = await session.get(Organization, org_id)
        assert organization is not None
        organization.monthly_ai_check_limit = 4
        await session.commit()

    async def reserve() -> bool:
        async with database.session() as session:
            try:
                await reserve_ai_check(session, org_id)
            except PlanLimitReached:
                await session.rollback()
                return False
            await session.commit()
            return True

    results = await asyncio.gather(*(reserve() for _ in range(20)))

    assert sum(results) == 4
    async with database.session() as session:
        organization = await session.get(Organization, org_id)
        assert organization is not None
        assert organization.ai_checks_reserved == 4
        assert await ai_check_limit_reached(session, org_id) is True


async def test_deleting_site_does_not_reset_ai_usage(database: Database) -> None:
    async with database.session() as session:
        org_id = await create_org(session, "Immutable ledger")
        organization = await session.get(Organization, org_id)
        assert organization is not None
        organization.monthly_ai_check_limit = 1
        await reserve_site_slot(session, org_id)
        site = Site(organization_id=org_id, url="https://usage.example")
        session.add(site)
        await session.flush()
        session.add(AIUsage(organization_id=org_id, site_id=site.id, model="gpt"))
        await session.commit()
        site_id = site.id

    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        await release_site_slot(session, org_id)
        await session.delete(site)
        await session.commit()

    async with database.session() as session:
        usage = (await session.execute(select(AIUsage))).scalar_one()
        assert usage.organization_id == org_id
        assert usage.site_id is None
        assert await ai_check_limit_reached(session, org_id) is True


async def test_usage_api_retains_deleted_site_cost_and_isolates_other_tenants(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    me = (await admin_client.get("/api/auth/me")).json()
    organization_id = me["organization_id"]
    site_response = await admin_client.post(
        "/api/sites",
        json={"url": "https://retained-usage.example"},
    )
    assert site_response.status_code == 201, site_response.text
    site_id = site_response.json()["id"]
    acting_headers = {"X-Acting-Org": str(organization_id)}

    async with database.session() as session:
        other_org_id = await create_org(session, "Other tenant")
        other_site = Site(
            organization_id=other_org_id,
            url="https://other-tenant.example",
        )
        session.add(other_site)
        await session.flush()
        session.add_all(
            [
                AIUsage(
                    organization_id=organization_id,
                    site_id=site_id,
                    model="gpt-visible",
                    total_tokens=41,
                    cost_usd=0.0123,
                ),
                AIUsage(
                    organization_id=other_org_id,
                    site_id=other_site.id,
                    model="gpt-hidden",
                    total_tokens=999,
                    cost_usd=9.99,
                ),
            ]
        )
        await session.commit()

    deleted = await admin_client.delete(f"/api/sites/{site_id}", headers=acting_headers)
    assert deleted.status_code == 204, deleted.text

    response = await admin_client.get("/api/usage/summary", headers=acting_headers)
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["calls"] == 1
    assert summary["total_tokens"] == 41
    assert summary["total_cost_usd"] == 0.0123
    assert [bucket["model"] for bucket in summary["by_model"]] == ["gpt-visible"]
    assert summary["by_site"] == []


async def test_suspended_org_cannot_run_any_capture_path(
    database: Database,
    settings: Settings,
    channel: RecordingChannel,
) -> None:
    async with database.session() as session:
        org_id = await create_org(session, "Suspended runner")
        organization = await session.get(Organization, org_id)
        assert organization is not None
        site = Site(organization_id=org_id, url="https://suspended.example")
        session.add(site)
        await session.flush()
        site_id = site.id
        organization.is_active = False
        await session.commit()

    capturer = ScriptedCapturer(html="<main>should never be captured</main>")
    runner = SiteRunner(
        database,
        capturer,
        settings,
        analyzer=StubAnalyzer(),
        channel=channel,
    )

    with pytest.raises(AccessDenied, match="suspended"):
        await runner.run(site_id)
    with pytest.raises(AccessDenied, match="suspended"):
        await runner.snapshot(site_id)
    assert capturer.calls == []


async def test_operator_manual_check_cannot_bypass_suspension(
    admin_client: httpx.AsyncClient,
) -> None:
    step_up = await admin_client.post("/api/auth/step-up", json={"password": "supersecret123"})
    assert step_up.status_code == 204, step_up.text
    organization = (
        await admin_client.post("/api/organizations", json={"name": "Manual suspension"})
    ).json()
    headers = {"X-Acting-Org": str(organization["id"])}
    site = await admin_client.post(
        "/api/sites",
        headers=headers,
        json={"url": "https://manual-suspended.example"},
    )
    assert site.status_code == 201, site.text
    step_up = await admin_client.post("/api/auth/step-up", json={"password": "supersecret123"})
    assert step_up.status_code == 204, step_up.text
    suspended = await admin_client.patch(
        f"/api/organizations/{organization['id']}",
        json={"is_active": False},
    )
    assert suspended.status_code == 200, suspended.text

    response = await admin_client.post(f"/api/sites/{site.json()['id']}/check", headers=headers)
    assert response.status_code == 403
