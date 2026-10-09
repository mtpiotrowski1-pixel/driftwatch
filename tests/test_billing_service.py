from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import driftwatch.billing.service as billing_service
from driftwatch.billing.provider import (
    BillingProviderError,
    CheckoutRequest,
    HostedSession,
    InvoiceSnapshot,
    PortalRequest,
    ProviderEvent,
    ProviderPrice,
    SubscriptionLine,
    SubscriptionSnapshot,
)
from driftwatch.billing.service import (
    BillingProjectionError,
    expire_billing_entitlements,
    ingest_provider_event,
    reconcile_customer,
)
from driftwatch.db import Database
from driftwatch.models import (
    BillingCustomer,
    BillingEvent,
    BillingEventProcessing,
    BillingPrice,
    EntitlementGrant,
    InvoiceReference,
    Organization,
    Plan,
    Subscription,
)


class ReconcileProvider:
    provider_name = "stripe"

    def __init__(self, snapshots: tuple[SubscriptionSnapshot, ...]) -> None:
        self.snapshots = snapshots

    async def list_subscriptions(self, customer_id: str) -> tuple[SubscriptionSnapshot, ...]:
        return self.snapshots

    async def create_checkout(self, request: CheckoutRequest) -> HostedSession:
        raise BillingProviderError

    async def create_portal(self, request: PortalRequest) -> HostedSession:
        raise BillingProviderError

    async def get_price(self, provider_price_id: str) -> ProviderPrice:
        raise BillingProviderError

    def verify_webhook(self, *args: object, **kwargs: object) -> ProviderEvent:
        raise BillingProviderError

    async def aclose(self) -> None:
        return None


async def _catalog(database: Database) -> tuple[int, int, int]:
    async with database.session() as session:
        plan = Plan(
            key="paid",
            name="Paid",
            max_sites=10,
            max_members=8,
            monthly_ai_check_limit=100,
            currency="USD",
            is_active=True,
            is_self_serve=True,
        )
        org = Organization(name="Acme")
        session.add_all([plan, org])
        await session.flush()
        customer = BillingCustomer(
            organization_id=org.id,
            provider="stripe",
            provider_customer_id="cus_acme",
        )
        price = BillingPrice(
            plan_id=plan.id,
            provider="stripe",
            provider_price_id="price_paid",
            version=1,
            unit_amount_minor=1900,
            currency="USD",
            recurring_interval="month",
            interval_count=1,
            is_active=True,
        )
        session.add_all([customer, price])
        await session.commit()
        return org.id, customer.id, plan.id


def _subscription_event(
    *,
    event_id: str,
    status: str = "active",
    prices: tuple[str, ...] = ("price_paid",),
    now: datetime,
    trial_end: datetime | None = None,
) -> ProviderEvent:
    return ProviderEvent(
        provider="stripe",
        event_id=event_id,
        event_type="customer.subscription.updated",
        occurred_at=now,
        received_at=now,
        livemode=False,
        api_version="2025-06-30.basil",
        payload_sha256=(event_id.encode().hex() + "0" * 64)[:64],
        resource=SubscriptionSnapshot(
            provider_subscription_id="sub_acme",
            provider_customer_id="cus_acme",
            status=status,
            organization_reference=None,
            items=tuple(
                SubscriptionLine(f"si_{index}", price, 1) for index, price in enumerate(prices)
            ),
            current_period_start=now - timedelta(days=1),
            current_period_end=now + timedelta(days=30),
            trial_end=trial_end,
        ),
    )


@pytest.mark.asyncio
async def test_mixed_known_and_unknown_prices_suspend_instead_of_granting(
    database: Database,
) -> None:
    org_id, _, _ = await _catalog(database)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    event = _subscription_event(
        event_id="evt_unknown",
        prices=("price_paid", "price_not_registered"),
        now=now,
    )

    async with database.session() as session:
        await ingest_provider_event(session, event, grace_days=7)
    async with database.session() as session:
        org = await session.get(Organization, org_id)
        subscription = (await session.execute(select(Subscription))).scalar_one()
        grant = (await session.execute(select(EntitlementGrant))).scalar_one()

    assert org is not None and org.is_active is False
    assert org.billing_suspended_at is not None
    assert subscription.plan_id is None
    assert grant.is_active is False
    assert grant.reason == "unmapped_price"


@pytest.mark.asyncio
async def test_paid_entitlement_copies_member_cap(database: Database) -> None:
    org_id, _, plan_id = await _catalog(database)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    async with database.session() as session:
        result = await ingest_provider_event(
            session,
            _subscription_event(event_id="evt_member_cap", now=now),
            grace_days=7,
        )
    async with database.session() as session:
        organization = await session.get(Organization, org_id)

    assert result.status == "processed"
    assert organization is not None
    assert organization.plan_id == plan_id
    assert organization.max_members == 8


@pytest.mark.asyncio
async def test_entitlement_expiry_sweep_suspends_expired_active_period(
    database: Database,
) -> None:
    org_id, _, _ = await _catalog(database)
    first = datetime(2026, 1, 1, tzinfo=UTC)
    async with database.session() as session:
        await ingest_provider_event(
            session,
            _subscription_event(event_id="evt_active", now=first),
            grace_days=7,
        )
    async with database.session() as session:
        await expire_billing_entitlements(
            session,
            now=first + timedelta(days=31),
            grace_days=7,
        )
        await session.commit()
    async with database.session() as session:
        org = await session.get(Organization, org_id)
        grant = (await session.execute(select(EntitlementGrant))).scalar_one()

    assert org is not None and org.is_active is False
    assert grant.is_active is False
    assert grant.reason == "period_expired"


@pytest.mark.asyncio
async def test_reconcile_closes_local_subscription_missing_from_full_provider_set(
    database: Database,
) -> None:
    org_id, customer_id, _ = await _catalog(database)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    async with database.session() as session:
        await ingest_provider_event(
            session,
            _subscription_event(event_id="evt_active", now=now),
            grace_days=7,
        )
    async with database.session() as session:
        customer = await session.get(BillingCustomer, customer_id)
        assert customer is not None
        result = await reconcile_customer(
            session,
            ReconcileProvider(()),
            customer,
            grace_days=7,
            now=now + timedelta(hours=1),
        )
    async with database.session() as session:
        org = await session.get(Organization, org_id)
        subscription = (await session.execute(select(Subscription))).scalar_one()

    assert result.subscriptions_seen == 0
    assert result.subscriptions_updated == 1
    assert subscription.status == "canceled"
    assert org is not None and org.is_active is False


@pytest.mark.asyncio
async def test_processed_event_is_idempotent(database: Database) -> None:
    await _catalog(database)
    event = _subscription_event(
        event_id="evt_duplicate",
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    async with database.session() as session:
        first = await ingest_provider_event(session, event, grace_days=7)
    async with database.session() as session:
        second = await ingest_provider_event(session, event, grace_days=7)
        processing = (await session.execute(select(BillingEventProcessing))).scalar_one()

    assert first.duplicate is False
    assert second.duplicate is True
    assert processing.status == "processed"
    assert processing.attempt_count == 1


@pytest.mark.asyncio
async def test_duplicate_insert_race_recovers_the_committed_event(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _catalog(database)
    event = _subscription_event(
        event_id="evt_insert_race",
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    async with database.session() as session:
        row = BillingEvent(
            provider=event.provider,
            provider_event_id=event.event_id,
            event_type=event.event_type,
            resource_id=event.resource_id,
            organization_id=None,
            occurred_at=event.occurred_at,
            received_at=event.received_at,
            livemode=event.livemode,
            api_version=event.api_version,
            payload_sha256=event.payload_sha256,
            resource_data=event.ledger_data(),
        )
        session.add(row)
        await session.flush()
        session.add(
            BillingEventProcessing(
                billing_event_id=row.id,
                status="processed",
                attempt_count=1,
                processed_at=event.received_at,
                updated_at=event.received_at,
            )
        )
        await session.commit()

    original_find = billing_service._find_event
    calls = 0

    async def raced_find(*args: object, **kwargs: object) -> BillingEvent | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        return await original_find(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(billing_service, "_find_event", raced_find)
    async with database.session() as session:
        result = await ingest_provider_event(session, event, grace_days=7)

    assert result.duplicate is True
    assert result.status == "processed"


@pytest.mark.asyncio
async def test_equal_timestamp_events_reconcile_provider_authoritative_state(
    database: Database,
) -> None:
    org_id, _, _ = await _catalog(database)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    first = _subscription_event(event_id="evt_z", status="active", now=now)
    conflicting = _subscription_event(event_id="evt_a", status="unpaid", now=now)
    assert isinstance(conflicting.resource, SubscriptionSnapshot)
    provider = ReconcileProvider((conflicting.resource,))

    async with database.session() as session:
        await ingest_provider_event(session, first, grace_days=7)
    async with database.session() as session:
        result = await ingest_provider_event(
            session,
            conflicting,
            grace_days=7,
            provider_client=provider,
        )
    async with database.session() as session:
        subscription = (await session.execute(select(Subscription))).scalar_one()
        organization = await session.get(Organization, org_id)

    assert result.status == "processed"
    assert subscription.status == "unpaid"
    assert subscription.last_event_id == "reconcile:sub_acme"
    assert organization is not None and organization.is_active is False


@pytest.mark.asyncio
async def test_reused_provider_event_id_with_different_payload_is_rejected(
    database: Database,
) -> None:
    await _catalog(database)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    event = _subscription_event(event_id="evt_reused", now=now)
    async with database.session() as session:
        await ingest_provider_event(session, event, grace_days=7)
    conflicting = ProviderEvent(
        provider=event.provider,
        event_id=event.event_id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        received_at=event.received_at,
        livemode=event.livemode,
        api_version=event.api_version,
        payload_sha256="f" * 64,
        resource=event.resource,
    )

    async with database.session() as session:
        with pytest.raises(BillingProjectionError, match="identity was reused"):
            await ingest_provider_event(session, conflicting, grace_days=7)


@pytest.mark.asyncio
async def test_concurrent_processing_claim_is_not_acknowledged_as_complete(
    database: Database,
) -> None:
    await _catalog(database)
    now = datetime.now(UTC)
    event = _subscription_event(event_id="evt_inflight", now=now)
    async with database.session() as session:
        row = BillingEvent(
            provider=event.provider,
            provider_event_id=event.event_id,
            event_type=event.event_type,
            resource_id=event.resource_id,
            organization_id=None,
            occurred_at=event.occurred_at,
            received_at=event.received_at,
            livemode=event.livemode,
            api_version=event.api_version,
            payload_sha256=event.payload_sha256,
            resource_data=event.ledger_data(),
        )
        session.add(row)
        await session.flush()
        session.add(
            BillingEventProcessing(
                billing_event_id=row.id,
                status="processing",
                attempt_count=1,
                updated_at=now,
            )
        )
        await session.commit()

    async with database.session() as session:
        with pytest.raises(BillingProjectionError, match="already being processed"):
            await ingest_provider_event(session, event, grace_days=7)


@pytest.mark.asyncio
async def test_unmapped_subscription_is_retried_after_customer_mapping_exists(
    database: Database,
) -> None:
    org_id, customer_id, _ = await _catalog(database)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    event = _subscription_event(event_id="evt_subscription_before_mapping", now=now)
    async with database.session() as session:
        customer = await session.get(BillingCustomer, customer_id)
        assert customer is not None
        await session.delete(customer)
        await session.commit()

    async with database.session() as session:
        with pytest.raises(BillingProjectionError, match="not mapped"):
            await ingest_provider_event(session, event, grace_days=7)
    async with database.session() as session:
        processing = (await session.execute(select(BillingEventProcessing))).scalar_one()
        assert processing.status == "failed"
        session.add(
            BillingCustomer(
                organization_id=org_id,
                provider="stripe",
                provider_customer_id="cus_acme",
            )
        )
        await session.commit()

    async with database.session() as session:
        result = await ingest_provider_event(session, event, grace_days=7)
    async with database.session() as session:
        processing = (await session.execute(select(BillingEventProcessing))).scalar_one()
        subscription = (await session.execute(select(Subscription))).scalar_one()

    assert result.duplicate is True
    assert result.status == "processed"
    assert processing.status == "processed"
    assert processing.attempt_count == 2
    assert subscription.organization_id == org_id


@pytest.mark.asyncio
async def test_invoice_before_subscription_is_retried_and_linked_after_mapping(
    database: Database,
) -> None:
    await _catalog(database)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    invoice_event = ProviderEvent(
        provider="stripe",
        event_id="evt_invoice_before_subscription",
        event_type="invoice.paid",
        occurred_at=now,
        received_at=now,
        livemode=False,
        api_version="2025-06-30.basil",
        payload_sha256="d" * 64,
        resource=InvoiceSnapshot(
            provider_invoice_id="in_before_subscription",
            provider_customer_id="cus_acme",
            provider_subscription_id="sub_acme",
            invoice_number="DW-0001",
            status="paid",
            currency="USD",
            amount_due_minor=1900,
            amount_paid_minor=1900,
            provider_created_at=now,
            paid_at=now,
        ),
    )

    async with database.session() as session:
        with pytest.raises(BillingProjectionError, match="not mapped to a subscription"):
            await ingest_provider_event(session, invoice_event, grace_days=7)
    async with database.session() as session:
        assert (await session.execute(select(InvoiceReference))).scalar_one_or_none() is None
        processing = (await session.execute(select(BillingEventProcessing))).scalar_one()
        assert processing.status == "failed"

    async with database.session() as session:
        await ingest_provider_event(
            session,
            _subscription_event(event_id="evt_subscription_mapping", now=now),
            grace_days=7,
        )
    async with database.session() as session:
        retried = await ingest_provider_event(session, invoice_event, grace_days=7)
    async with database.session() as session:
        invoice = (await session.execute(select(InvoiceReference))).scalar_one()
        subscription = (await session.execute(select(Subscription))).scalar_one()
        invoice_processing = (
            await session.execute(
                select(BillingEventProcessing)
                .join(BillingEvent)
                .where(BillingEvent.provider_event_id == invoice_event.event_id)
            )
        ).scalar_one()

    assert retried.duplicate is True
    assert invoice.subscription_id == subscription.id
    assert invoice_processing.status == "processed"
    assert invoice_processing.attempt_count == 2
