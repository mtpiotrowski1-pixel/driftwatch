"""Durable webhook ingestion, billing projections, and reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.billing.access import lock_organization_access
from driftwatch.billing.provider import (
    BillingProvider,
    CheckoutSnapshot,
    InvoiceSnapshot,
    ProviderEvent,
    ReconciliationResult,
    SubscriptionLine,
    SubscriptionSnapshot,
    subscription_access_decision,
    utcnow,
)
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
    SubscriptionItem,
)

BILLING_EVENT_PROCESSING_STALE_AFTER = timedelta(minutes=5)


class BillingProjectionError(Exception):
    """A verified and persisted event could not be projected."""


@dataclass(frozen=True, slots=True)
class IngestResult:
    event_id: int
    status: str
    duplicate: bool


async def ingest_provider_event(
    session: AsyncSession,
    event: ProviderEvent,
    *,
    grace_days: int,
    provider_client: BillingProvider | None = None,
) -> IngestResult:
    """Commit the immutable event before applying its mutable projections."""
    existing = await _find_event(session, event.provider, event.event_id)
    duplicate = existing is not None
    if existing is None:
        row = BillingEvent(
            provider=event.provider,
            provider_event_id=event.event_id,
            event_type=event.event_type,
            resource_id=event.resource_id,
            organization_id=await _event_organization_id(session, event),
            occurred_at=event.occurred_at,
            received_at=event.received_at,
            livemode=event.livemode,
            api_version=event.api_version,
            payload_sha256=event.payload_sha256,
            resource_data=event.ledger_data(),
        )
        session.add(row)
        try:
            await session.flush()
            session.add(BillingEventProcessing(billing_event_id=row.id, status="received"))
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await _find_event(session, event.provider, event.event_id)
            if existing is None:
                raise
            row = existing
            duplicate = True
    else:
        row = existing

    if (
        row.payload_sha256 != event.payload_sha256
        or row.event_type != event.event_type
        or row.livemode != event.livemode
    ):
        raise BillingProjectionError("Provider event identity was reused with different data")

    billing_event_id = row.id
    processing = await session.get(BillingEventProcessing, billing_event_id)
    if processing is None:
        raise BillingProjectionError("Billing event processing state is missing")
    if processing.status in {
        "processed",
        "ignored_out_of_order",
        "ignored_unsupported",
    }:
        return IngestResult(billing_event_id, processing.status, True)

    claim_time = utcnow()
    stale_before = claim_time - BILLING_EVENT_PROCESSING_STALE_AFTER
    claimed = await session.execute(
        update(BillingEventProcessing)
        .where(
            BillingEventProcessing.billing_event_id == billing_event_id,
            or_(
                BillingEventProcessing.status.in_({"received", "failed", "ignored_unmapped"}),
                (
                    (BillingEventProcessing.status == "processing")
                    & (BillingEventProcessing.updated_at < stale_before)
                ),
            ),
        )
        .values(
            status="processing",
            attempt_count=BillingEventProcessing.attempt_count + 1,
            last_error_code=None,
            updated_at=claim_time,
        )
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:  # type: ignore[attr-defined]
        await session.rollback()
        current = await session.get(BillingEventProcessing, billing_event_id)
        if current is not None and current.status == "processing":
            raise BillingProjectionError("Billing event is already being processed")
        return IngestResult(billing_event_id, current.status if current else "unknown", True)
    await session.commit()
    try:
        outcome = await _project_event(
            session,
            event,
            grace_days=grace_days,
            provider_client=provider_client,
        )
        processing = await session.get(BillingEventProcessing, billing_event_id)
        if processing is None:
            raise BillingProjectionError("Billing event processing state is missing")
        processing.status = outcome
        processing.processed_at = utcnow()
        processing.last_error_code = None
        await session.commit()
        return IngestResult(billing_event_id, outcome, duplicate)
    except Exception as exc:
        await session.rollback()
        processing = await session.get(BillingEventProcessing, billing_event_id)
        if processing is not None:
            processing.status = "failed"
            processing.last_error_code = type(exc).__name__[:80]
            await session.commit()
        if isinstance(exc, BillingProjectionError):
            raise
        raise BillingProjectionError("Verified billing event projection failed") from exc


async def reconcile_customer(
    session: AsyncSession,
    provider: BillingProvider,
    customer: BillingCustomer,
    *,
    grace_days: int,
    now: datetime | None = None,
) -> ReconciliationResult:
    reconciled_at = (now or utcnow()).astimezone(UTC)
    locked_customer = await _lock_customer_by_id(session, customer.id)
    if locked_customer is None:
        raise BillingProjectionError("Billing customer no longer exists")
    if (
        locked_customer.provider != provider.provider_name
        or locked_customer.provider_customer_id != customer.provider_customer_id
    ):
        raise BillingProjectionError("Provider reconciliation crossed customer boundaries")
    customer = locked_customer
    snapshots = await provider.list_subscriptions(customer.provider_customer_id)
    await _require_locked_organization(session, customer.organization_id)
    seen_ids: set[str] = set()
    updated = 0
    for snapshot in snapshots:
        if snapshot.provider_customer_id != customer.provider_customer_id:
            raise BillingProjectionError("Provider reconciliation crossed customer boundaries")
        if snapshot.provider_subscription_id in seen_ids:
            raise BillingProjectionError(
                "Provider reconciliation returned a duplicate subscription"
            )
        seen_ids.add(snapshot.provider_subscription_id)
        outcome = await _project_subscription(
            session,
            provider=provider.provider_name,
            snapshot=snapshot,
            event_id=f"reconcile:{snapshot.provider_subscription_id}",
            event_time=reconciled_at,
            now=reconciled_at,
            grace_days=grace_days,
            force=True,
            known_customer=customer,
        )
        if outcome == "processed":
            updated += 1
    local_subscriptions = (
        (
            await session.execute(
                select(Subscription).where(
                    Subscription.billing_customer_id == customer.id,
                    Subscription.provider == provider.provider_name,
                )
            )
        )
        .scalars()
        .all()
    )
    for subscription in local_subscriptions:
        if subscription.provider_subscription_id in seen_ids:
            continue
        if subscription.status in {"canceled", "incomplete_expired"}:
            continue
        subscription.status = "canceled"
        subscription.canceled_at = subscription.canceled_at or reconciled_at
        subscription.last_event_at = reconciled_at
        subscription.last_event_id = f"reconcile:missing:{subscription.provider_subscription_id}"
        updated += 1
    await _recompute_organization_access(
        session,
        organization_id=customer.organization_id,
        now=reconciled_at,
        grace_days=grace_days,
    )
    customer.last_reconciled_at = reconciled_at
    await session.commit()
    return ReconciliationResult(
        customer_id=customer.id,
        subscriptions_seen=len(snapshots),
        subscriptions_updated=updated,
    )


async def _project_event(
    session: AsyncSession,
    event: ProviderEvent,
    *,
    grace_days: int,
    provider_client: BillingProvider | None,
) -> str:
    resource = event.resource
    if isinstance(resource, CheckoutSnapshot):
        customer = await _upsert_customer(
            session,
            provider=event.provider,
            customer_id=resource.provider_customer_id,
            organization_reference=resource.organization_reference,
        )
        if customer is None:
            raise BillingProjectionError("Billing resource is not mapped to an organization")
        if (
            resource.terms_version
            and resource.privacy_version
            and (
                customer.consented_at is None
                or _as_utc(event.occurred_at) >= _as_utc(customer.consented_at)
            )
        ):
            customer.terms_version = resource.terms_version
            customer.privacy_version = resource.privacy_version
            customer.terms_sha256 = resource.terms_sha256
            customer.privacy_sha256 = resource.privacy_sha256
            customer.consented_at = event.occurred_at
            customer.consented_by_user_id = resource.consented_by_user_id
        return "processed"
    if isinstance(resource, SubscriptionSnapshot):
        return await _project_subscription(
            session,
            provider=event.provider,
            snapshot=resource,
            event_id=event.event_id,
            event_time=event.occurred_at,
            now=event.received_at,
            grace_days=grace_days,
            force=False,
            provider_client=provider_client,
        )
    if isinstance(resource, InvoiceSnapshot):
        return await _project_invoice(session, event.provider, resource, event.occurred_at)
    return "ignored_unsupported"


async def _project_subscription(
    session: AsyncSession,
    *,
    provider: str,
    snapshot: SubscriptionSnapshot,
    event_id: str,
    event_time: datetime,
    now: datetime,
    grace_days: int,
    force: bool,
    known_customer: BillingCustomer | None = None,
    provider_client: BillingProvider | None = None,
) -> str:
    if known_customer is not None:
        customer = await _lock_customer_by_id(session, known_customer.id)
        if customer is not None and (
            customer.provider != provider
            or customer.provider_customer_id != snapshot.provider_customer_id
        ):
            raise BillingProjectionError("Provider subscription changed customer ownership")
    else:
        customer = await _upsert_customer(
            session,
            provider=provider,
            customer_id=snapshot.provider_customer_id,
            organization_reference=snapshot.organization_reference,
        )
    if customer is None:
        raise BillingProjectionError("Billing resource is not mapped to an organization")
    await _require_locked_organization(session, customer.organization_id)
    subscription = (
        await session.execute(
            select(Subscription).where(
                Subscription.provider == provider,
                Subscription.provider_subscription_id == snapshot.provider_subscription_id,
            )
        )
    ).scalar_one_or_none()
    if not force and subscription is not None and subscription.last_event_at is not None:
        event_at = _as_utc(event_time)
        previous_at = _as_utc(subscription.last_event_at)
        if event_at < previous_at or (
            event_at == previous_at and event_id == subscription.last_event_id
        ):
            return "ignored_out_of_order"
        if event_at == previous_at:
            # Stripe event ids do not define order and event.created is only
            # second-granular. Resolve a same-second conflict from provider
            # state instead of granting/revoking access by arbitrary id order.
            if provider_client is None or provider_client.provider_name != provider:
                raise BillingProjectionError(
                    "Same-timestamp subscription events require provider reconciliation"
                )
            await reconcile_customer(
                session,
                provider_client,
                customer,
                grace_days=grace_days,
                now=now,
            )
            return "processed"
    if subscription is None:
        subscription = Subscription(
            organization_id=customer.organization_id,
            billing_customer_id=customer.id,
            provider=provider,
            provider_subscription_id=snapshot.provider_subscription_id,
            status=snapshot.status,
        )
        session.add(subscription)
        await session.flush()
    elif (
        subscription.organization_id != customer.organization_id
        or subscription.billing_customer_id != customer.id
    ):
        raise BillingProjectionError("Provider subscription changed tenant ownership")

    previous_status = subscription.status
    subscription.status = snapshot.status
    subscription.current_period_start = snapshot.current_period_start
    subscription.current_period_end = snapshot.current_period_end
    subscription.trial_end = snapshot.trial_end
    subscription.cancel_at_period_end = snapshot.cancel_at_period_end
    subscription.canceled_at = snapshot.canceled_at
    subscription.last_event_at = event_time
    subscription.last_event_id = event_id
    if snapshot.status == "past_due":
        if previous_status != "past_due" or subscription.past_due_since is None:
            subscription.past_due_since = event_time
    else:
        subscription.past_due_since = None

    subscription.plan_id = await _sync_subscription_items(
        session,
        subscription,
        provider=provider,
        snapshots=snapshot.items,
    )
    await _recompute_organization_access(
        session,
        organization_id=subscription.organization_id,
        now=now,
        grace_days=grace_days,
    )
    return "processed"


async def _sync_subscription_items(
    session: AsyncSession,
    subscription: Subscription,
    *,
    provider: str,
    snapshots: tuple[SubscriptionLine, ...],
) -> int | None:
    lines = list(snapshots)
    price_ids = {line.provider_price_id for line in lines}
    prices = (
        (
            await session.execute(
                select(BillingPrice).where(
                    BillingPrice.provider == provider,
                    BillingPrice.provider_price_id.in_(price_ids),
                )
            )
        )
        .scalars()
        .all()
        if price_ids
        else []
    )
    price_by_provider_id = {price.provider_price_id: price for price in prices}
    if len(price_by_provider_id) != len(price_ids):
        mapped_plan_id: int | None = None
    else:
        mapped_plan_id = next(iter({price.plan_id for price in prices}), None)
    plan_ids = {price.plan_id for price in prices}
    if len(plan_ids) > 1:
        raise BillingProjectionError("A subscription contains prices from multiple plans")
    existing = (
        (
            await session.execute(
                select(SubscriptionItem).where(SubscriptionItem.subscription_id == subscription.id)
            )
        )
        .scalars()
        .all()
    )
    existing_by_provider_id = {item.provider_item_id: item for item in existing}
    seen: set[str] = set()
    for line in lines:
        seen.add(line.provider_item_id)
        item = existing_by_provider_id.get(line.provider_item_id)
        if item is None:
            item = SubscriptionItem(
                subscription_id=subscription.id,
                provider_item_id=line.provider_item_id,
                provider_price_id=line.provider_price_id,
                quantity=line.quantity,
            )
            session.add(item)
        item.provider_price_id = line.provider_price_id
        item.quantity = line.quantity
        price = price_by_provider_id.get(line.provider_price_id)
        item.billing_price_id = price.id if price is not None else None
    for item in existing:
        if item.provider_item_id not in seen:
            await session.delete(item)
    return mapped_plan_id


async def expire_billing_entitlements(
    session: AsyncSession,
    *,
    now: datetime,
    grace_days: int,
) -> int:
    """Re-evaluate time-bounded access without waiting for a provider webhook."""
    organization_ids = (
        await session.execute(
            select(Subscription.organization_id).distinct().order_by(Subscription.organization_id)
        )
    ).scalars()
    refreshed = 0
    for organization_id in organization_ids:
        await _lock_organization_customers(session, organization_id)
        await _recompute_organization_access(
            session,
            organization_id=organization_id,
            now=now,
            grace_days=grace_days,
        )
        refreshed += 1
    return refreshed


async def _recompute_organization_access(
    session: AsyncSession,
    *,
    organization_id: int,
    now: datetime,
    grace_days: int,
) -> None:
    organization = await _require_locked_organization(session, organization_id)
    subscriptions = (
        (
            await session.execute(
                select(Subscription).where(Subscription.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    entitled: list[Subscription] = []
    should_suspend = False
    has_unmapped_subscription = False
    for subscription in subscriptions:
        decision = subscription_access_decision(
            subscription.status,
            now=_as_utc(now),
            past_due_since=subscription.past_due_since,
            grace_days=grace_days,
            trial_end=subscription.trial_end,
            current_period_end=subscription.current_period_end,
        )
        grant = (
            await session.execute(
                select(EntitlementGrant).where(
                    EntitlementGrant.subscription_id == subscription.id,
                    EntitlementGrant.entitlement_key == "plan_access",
                )
            )
        ).scalar_one_or_none()
        if grant is None:
            grant = EntitlementGrant(
                organization_id=organization_id,
                subscription_id=subscription.id,
                plan_id=subscription.plan_id,
                entitlement_key="plan_access",
                reason=decision.reason,
            )
            session.add(grant)
        grant.plan_id = subscription.plan_id
        if subscription.plan_id is None and decision.entitled:
            has_unmapped_subscription = True
        grant.is_active = decision.entitled and subscription.plan_id is not None
        grant.valid_until = decision.valid_until
        grant.reason = decision.reason if subscription.plan_id is not None else "unmapped_price"
        grant.revoked_at = None if grant.is_active else now
        if grant.is_active:
            entitled.append(subscription)
            subscription.access_suspended_at = None
        elif decision.suspend or subscription.plan_id is None:
            subscription.access_suspended_at = subscription.access_suspended_at or now
            should_suspend = True

    if entitled and not has_unmapped_subscription:
        selected = max(
            entitled,
            key=lambda item: (_as_utc(item.current_period_end), item.id),
        )
        plan = await session.get(Plan, selected.plan_id)
        if plan is None:
            raise BillingProjectionError("An entitled billing plan no longer exists")
        organization.plan_id = plan.id
        organization.plan = plan.key
        organization.max_sites = plan.max_sites
        organization.max_members = plan.max_members
        organization.monthly_ai_check_limit = plan.monthly_ai_check_limit
        if organization.billing_suspended_at is not None:
            organization.billing_suspended_at = None
        organization.is_active = organization.manually_suspended_at is None
        return

    if should_suspend:
        organization.billing_suspended_at = organization.billing_suspended_at or now
        organization.is_active = False


async def _project_invoice(
    session: AsyncSession,
    provider: str,
    snapshot: InvoiceSnapshot,
    event_time: datetime,
) -> str:
    customer = await _lock_customer(
        session,
        provider=provider,
        customer_id=snapshot.provider_customer_id,
    )
    if customer is None:
        raise BillingProjectionError("Billing resource is not mapped to an organization")
    subscription_id: int | None = None
    if snapshot.provider_subscription_id:
        subscription_id = (
            await session.execute(
                select(Subscription.id).where(
                    Subscription.provider == provider,
                    Subscription.provider_subscription_id == snapshot.provider_subscription_id,
                    Subscription.organization_id == customer.organization_id,
                )
            )
        ).scalar_one_or_none()
        if subscription_id is None:
            raise BillingProjectionError("Billing resource is not mapped to a subscription")
    invoice = (
        await session.execute(
            select(InvoiceReference).where(
                InvoiceReference.provider == provider,
                InvoiceReference.provider_invoice_id == snapshot.provider_invoice_id,
            )
        )
    ).scalar_one_or_none()
    if invoice is not None and _as_utc(event_time) < _as_utc(invoice.last_event_at):
        return "ignored_out_of_order"
    if invoice is None:
        invoice = InvoiceReference(
            organization_id=customer.organization_id,
            billing_customer_id=customer.id,
            provider=provider,
            provider_invoice_id=snapshot.provider_invoice_id,
            status=snapshot.status,
            currency=snapshot.currency,
            last_event_at=event_time,
        )
        session.add(invoice)
    invoice.subscription_id = subscription_id
    invoice.invoice_number = snapshot.invoice_number
    invoice.status = snapshot.status
    invoice.currency = snapshot.currency
    invoice.amount_due_minor = snapshot.amount_due_minor
    invoice.amount_paid_minor = snapshot.amount_paid_minor
    invoice.provider_created_at = snapshot.provider_created_at
    invoice.due_at = snapshot.due_at
    invoice.paid_at = snapshot.paid_at
    invoice.last_event_at = event_time
    return "processed"


async def _upsert_customer(
    session: AsyncSession,
    *,
    provider: str,
    customer_id: str,
    organization_reference: str | None,
) -> BillingCustomer | None:
    customer = await _lock_customer(
        session,
        provider=provider,
        customer_id=customer_id,
    )
    organization_id = _organization_id(organization_reference)
    if customer is not None:
        if organization_id is not None and organization_id != customer.organization_id:
            raise BillingProjectionError("Provider customer changed tenant ownership")
        return customer
    if organization_id is None or await session.get(Organization, organization_id) is None:
        return None
    customer = BillingCustomer(
        organization_id=organization_id,
        provider=provider,
        provider_customer_id=customer_id,
    )
    session.add(customer)
    await session.flush()
    return customer


async def _lock_customer(
    session: AsyncSession,
    *,
    provider: str,
    customer_id: str,
) -> BillingCustomer | None:
    return (
        await session.execute(
            select(BillingCustomer)
            .where(
                BillingCustomer.provider == provider,
                BillingCustomer.provider_customer_id == customer_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def _lock_customer_by_id(
    session: AsyncSession,
    customer_id: int,
) -> BillingCustomer | None:
    return (
        await session.execute(
            select(BillingCustomer)
            .where(BillingCustomer.id == customer_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def _lock_organization_customers(
    session: AsyncSession,
    organization_id: int,
) -> None:
    await session.execute(
        select(BillingCustomer)
        .where(BillingCustomer.organization_id == organization_id)
        .order_by(BillingCustomer.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _require_locked_organization(
    session: AsyncSession,
    organization_id: int,
) -> Organization:
    organization = await lock_organization_access(session, organization_id)
    if organization is None:
        raise BillingProjectionError("Billing organization no longer exists")
    return organization


async def _event_organization_id(session: AsyncSession, event: ProviderEvent) -> int | None:
    resource = event.resource
    reference = (
        resource.organization_reference
        if isinstance(resource, (CheckoutSnapshot, SubscriptionSnapshot))
        else None
    )
    organization_id = _organization_id(reference)
    if organization_id is not None:
        return organization_id
    customer_id = getattr(resource, "provider_customer_id", None)
    if not isinstance(customer_id, str):
        return None
    return (
        await session.execute(
            select(BillingCustomer.organization_id).where(
                BillingCustomer.provider == event.provider,
                BillingCustomer.provider_customer_id == customer_id,
            )
        )
    ).scalar_one_or_none()


async def _find_event(
    session: AsyncSession, provider: str, provider_event_id: str
) -> BillingEvent | None:
    return (
        await session.execute(
            select(BillingEvent).where(
                BillingEvent.provider == provider,
                BillingEvent.provider_event_id == provider_event_id,
            )
        )
    ).scalar_one_or_none()


def _organization_id(value: str | None) -> int | None:
    if value is None or not value.isdigit():
        return None
    result = int(value)
    return result if result > 0 else None


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
