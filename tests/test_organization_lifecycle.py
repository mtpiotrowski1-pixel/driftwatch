"""Organization offboarding preserves the records needed to operate the product."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from driftwatch.api.deps import STEP_UP_COOKIE
from driftwatch.billing.provider import ProviderEvent, SubscriptionLine, SubscriptionSnapshot
from driftwatch.billing.service import ingest_provider_event
from driftwatch.db import Database
from driftwatch.models import (
    AuditEvent,
    BillingCustomer,
    BillingPrice,
    Organization,
    Plan,
    Subscription,
)


async def _create_organization(client: httpx.AsyncClient) -> int:
    await _step_up(client)
    response = await client.post("/api/organizations", json={"name": "Lifecycle customer"})
    assert response.status_code == 201, response.text
    client.cookies.delete(STEP_UP_COOKIE)
    return int(response.json()["id"])


async def _step_up(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/auth/step-up", json={"password": "supersecret123"})
    assert response.status_code == 204, response.text


async def test_hard_delete_is_disabled_and_suspension_preserves_history(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    organization_id = await _create_organization(admin_client)
    async with database.session() as session:
        customer = BillingCustomer(
            organization_id=organization_id,
            provider="stripe",
            provider_customer_id="cus_lifecycle_guard",
        )
        session.add(customer)
        await session.flush()
        session.add(
            Subscription(
                organization_id=organization_id,
                billing_customer_id=customer.id,
                provider="stripe",
                provider_subscription_id="sub_lifecycle_guard",
                status="canceled",
            )
        )
        await session.commit()

    listed = await admin_client.get("/api/organizations")
    managed = next(item for item in listed.json() if item["id"] == organization_id)
    assert managed["billing_managed"] is True
    assert managed["billing_suspended"] is False

    # The compatibility route remains privileged, but even a stepped-up operator
    # cannot erase a tenant ledger through the product API.
    assert (await admin_client.delete(f"/api/organizations/{organization_id}")).status_code == 428
    await _step_up(admin_client)
    rejected = await admin_client.delete(f"/api/organizations/{organization_id}")
    assert rejected.status_code == 409
    assert "suspend the organization" in rejected.json()["detail"]

    entitlement_change = await admin_client.patch(
        f"/api/organizations/{organization_id}", json={"max_sites": 99}
    )
    assert entitlement_change.status_code == 409
    assert "billing-managed" in entitlement_change.json()["detail"]

    suspended = await admin_client.patch(
        f"/api/organizations/{organization_id}", json={"is_active": False}
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["is_active"] is False

    async with database.session() as session:
        organization = await session.get(Organization, organization_id)
        assert organization is not None
        assert organization.is_active is False
        assert organization.billing_suspended_at is None
        assert organization.max_sites is None
        customer = (
            await session.execute(
                select(BillingCustomer).where(
                    BillingCustomer.provider_customer_id == "cus_lifecycle_guard"
                )
            )
        ).scalar_one()
        assert customer.organization_id == organization_id
        event = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "organization.updated",
                    AuditEvent.target_id == str(organization_id),
                )
            )
        ).scalar_one()
        assert event.details["changes"]["is_active"] == {"from": True, "to": False}


async def test_operator_cannot_bypass_billing_suspension(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    organization_id = await _create_organization(admin_client)
    async with database.session() as session:
        organization = await session.get(Organization, organization_id)
        assert organization is not None
        organization.is_active = False
        organization.billing_suspended_at = datetime.now(UTC)
        await session.commit()

    await _step_up(admin_client)
    response = await admin_client.patch(
        f"/api/organizations/{organization_id}", json={"is_active": True}
    )

    assert response.status_code == 409
    assert "suspended by billing" in response.json()["detail"]


async def test_paid_event_never_reactivates_a_manually_suspended_tenant(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    organization_id = await _create_organization(admin_client)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    async with database.session() as session:
        plan = Plan(
            key="manual-suspension-paid",
            name="Manual suspension paid",
            max_sites=10,
            max_members=5,
            monthly_ai_check_limit=50,
            currency="USD",
        )
        session.add(plan)
        await session.flush()
        session.add_all(
            [
                BillingPrice(
                    plan_id=plan.id,
                    provider="stripe",
                    provider_price_id="price_manual_suspension",
                    version=1,
                    unit_amount_minor=1900,
                    currency="USD",
                    recurring_interval="month",
                    interval_count=1,
                ),
                BillingCustomer(
                    organization_id=organization_id,
                    provider="stripe",
                    provider_customer_id="cus_manual_suspension",
                ),
            ]
        )
        await session.commit()

    await _step_up(admin_client)
    suspended = await admin_client.patch(
        f"/api/organizations/{organization_id}",
        json={"is_active": False},
    )
    assert suspended.status_code == 200, suspended.text
    async with database.session() as session:
        organization = await session.get(Organization, organization_id)
        assert organization is not None
        assert organization.manually_suspended_at is not None
        # The tenant can be suspended for both reasons at once. A later paid
        # event is allowed to clear only the billing-owned reason. Preserve an
        # intentionally inconsistent active flag to prove recomputation also
        # repairs legacy/stale rows when the manual marker is authoritative.
        organization.billing_suspended_at = now
        organization.is_active = True
        await session.commit()

    paid_event = ProviderEvent(
        provider="stripe",
        event_id="evt_paid_manual_suspension",
        event_type="customer.subscription.updated",
        occurred_at=now + timedelta(minutes=1),
        received_at=now + timedelta(minutes=1),
        livemode=False,
        api_version="2025-06-30.basil",
        payload_sha256="c" * 64,
        resource=SubscriptionSnapshot(
            provider_subscription_id="sub_manual_suspension",
            provider_customer_id="cus_manual_suspension",
            status="active",
            organization_reference=None,
            items=(
                SubscriptionLine(
                    "si_manual_suspension",
                    "price_manual_suspension",
                    1,
                ),
            ),
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        ),
    )
    async with database.session() as session:
        await ingest_provider_event(session, paid_event, grace_days=7)
    async with database.session() as session:
        organization = await session.get(Organization, organization_id)
        assert organization is not None
        assert organization.billing_suspended_at is None
        assert organization.manually_suspended_at is not None
        assert organization.is_active is False

    await _step_up(admin_client)
    restored = await admin_client.patch(
        f"/api/organizations/{organization_id}",
        json={"is_active": True},
    )
    assert restored.status_code == 200, restored.text
    async with database.session() as session:
        organization = await session.get(Organization, organization_id)
        assert organization is not None
        assert organization.manually_suspended_at is None
        assert organization.is_active is True
