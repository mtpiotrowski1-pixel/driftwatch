"""Billing control plane, hosted customer sessions, and signed webhooks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.api.deps import (
    AdminUser,
    ExplicitOrgContext,
    InstanceSuperadminUser,
    SessionDep,
    SettingsDep,
    StepUpUser,
    SuperadminUser,
)
from driftwatch.audit import record_audit_event
from driftwatch.billing.plan_contract import lock_plan_contract
from driftwatch.billing.provider import (
    BillingProvider,
    BillingProviderError,
    CheckoutRequest,
    HostedSession,
    PortalRequest,
    ProviderPrice,
    WebhookVerificationError,
    validate_hosted_session,
)
from driftwatch.billing.schemas import (
    BillingCatalogOut,
    BillingCatalogPriceOut,
    BillingPriceCreate,
    BillingPriceOut,
    BillingStatusOut,
    CheckoutCreate,
    HostedSessionOut,
    PortalCreate,
    ReconciliationOut,
    SubscriptionStatusOut,
    WebhookAcceptedOut,
)
from driftwatch.billing.service import (
    BillingProjectionError,
    expire_billing_entitlements,
    ingest_provider_event,
    reconcile_customer,
)
from driftwatch.config import Settings
from driftwatch.models import (
    BillingCustomer,
    BillingPrice,
    CheckoutAttempt,
    EntitlementGrant,
    Plan,
    Subscription,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])

_CHECKOUT_PENDING_RECOVERY_AFTER = timedelta(minutes=5)
_CHECKOUT_PENDING_ABANDON_AFTER = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class _CheckoutReservation:
    attempt: CheckoutAttempt
    recovered_pending: bool = False
    recovered_age_seconds: int | None = None
    abandoned_attempt_id: int | None = None
    abandoned_age_seconds: int | None = None


def get_billing_provider(request: Request) -> BillingProvider:
    return request.app.state.billing_provider  # type: ignore[no-any-return]


BillingProviderDep = Annotated[BillingProvider, Depends(get_billing_provider)]


@router.get("/status", response_model=BillingStatusOut)
async def billing_status(
    session: SessionDep,
    settings: SettingsDep,
    provider: BillingProviderDep,
    _: AdminUser,
    organization_id: ExplicitOrgContext,
) -> BillingStatusOut:
    await expire_billing_entitlements(
        session,
        now=datetime.now(UTC),
        grace_days=settings.billing_past_due_grace_days,
    )
    customer = await _customer_for_org(session, organization_id, settings.billing_provider)
    subscription = (
        (
            await session.execute(
                select(Subscription)
                .where(Subscription.organization_id == organization_id)
                .order_by(Subscription.last_event_at.desc(), Subscription.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if customer is not None
        else None
    )
    subscription_out: SubscriptionStatusOut | None = None
    if subscription is not None:
        plan = await session.get(Plan, subscription.plan_id) if subscription.plan_id else None
        grant = (
            await session.execute(
                select(EntitlementGrant).where(
                    EntitlementGrant.subscription_id == subscription.id,
                    EntitlementGrant.entitlement_key == "plan_access",
                )
            )
        ).scalar_one_or_none()
        subscription_out = SubscriptionStatusOut(
            status=subscription.status,
            plan_id=subscription.plan_id,
            plan_key=plan.key if plan is not None else None,
            plan_name=plan.name if plan is not None else None,
            current_period_end=subscription.current_period_end,
            trial_end=subscription.trial_end,
            cancel_at_period_end=subscription.cancel_at_period_end,
            entitlement_active=grant.is_active if grant is not None else False,
            entitlement_valid_until=grant.valid_until if grant is not None else None,
            access_suspended_at=subscription.access_suspended_at,
        )
    return BillingStatusOut(
        provider=settings.billing_provider,
        provider_configured=settings.billing_provider_configured,
        self_serve_ready=(
            settings.billing_self_serve_ready
            and provider.provider_name == settings.billing_provider
        ),
        customer_exists=customer is not None,
        subscription=subscription_out,
    )


@router.get("/catalog", response_model=BillingCatalogOut)
async def billing_catalog(
    session: SessionDep,
    settings: SettingsDep,
    provider: BillingProviderDep,
    _: AdminUser,
    _organization_id: ExplicitOrgContext,
) -> BillingCatalogOut:
    ready = (
        settings.billing_self_serve_ready and provider.provider_name == settings.billing_provider
    )
    if not ready:
        return BillingCatalogOut(self_serve_ready=False, prices=[])

    rows = (
        await session.execute(
            select(BillingPrice, Plan)
            .join(Plan, Plan.id == BillingPrice.plan_id)
            .where(
                BillingPrice.provider == settings.billing_provider,
                BillingPrice.is_active.is_(True),
                Plan.is_active.is_(True),
                Plan.is_self_serve.is_(True),
            )
            .order_by(Plan.sort_order, Plan.id)
        )
    ).all()
    prices = [
        BillingCatalogPriceOut(
            billing_price_id=price.id,
            price_version=price.version,
            plan_id=plan.id,
            plan_key=plan.key,
            plan_name=plan.name,
            max_sites=plan.max_sites,
            max_members=plan.max_members,
            monthly_ai_check_limit=plan.monthly_ai_check_limit,
            unit_amount_minor=price.unit_amount_minor,
            currency=price.currency,
            recurring_interval=price.recurring_interval,
            interval_count=price.interval_count,
        )
        for price, plan in rows
    ]
    return BillingCatalogOut(
        self_serve_ready=True,
        terms_version=settings.billing_terms_version,
        privacy_version=settings.billing_privacy_version,
        terms_url=settings.billing_terms_url,
        privacy_url=settings.billing_privacy_url,
        terms_sha256=settings.billing_terms_sha256,
        privacy_sha256=settings.billing_privacy_sha256,
        prices=prices,
    )


@router.post("/checkout", response_model=HostedSessionOut)
async def create_checkout(
    payload: CheckoutCreate,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    provider: BillingProviderDep,
    admin: AdminUser,
    _: StepUpUser,
    organization_id: ExplicitOrgContext,
) -> HostedSessionOut:
    _require_self_serve(settings, provider)
    if (
        payload.accepted_terms_version != settings.billing_terms_version
        or payload.accepted_privacy_version != settings.billing_privacy_version
        or payload.accepted_terms_sha256 != settings.billing_terms_sha256
        or payload.accepted_privacy_sha256 != settings.billing_privacy_sha256
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The current terms and privacy policy versions must be accepted",
        )
    row = (
        await session.execute(
            select(BillingPrice, Plan)
            .join(Plan, Plan.id == BillingPrice.plan_id)
            .where(
                BillingPrice.id == payload.billing_price_id,
                BillingPrice.provider == settings.billing_provider,
                BillingPrice.is_active.is_(True),
                Plan.is_active.is_(True),
                Plan.is_self_serve.is_(True),
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Billing price is not available")
    price, _plan = row
    await _verify_provider_price(provider, price)
    active_subscription = (
        await session.execute(
            select(Subscription.id).where(
                Subscription.organization_id == organization_id,
                Subscription.status.not_in({"canceled", "incomplete_expired"}),
            )
        )
    ).first()
    if active_subscription is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An existing subscription must be managed through the billing portal",
        )
    customer = await _customer_for_org(session, organization_id, settings.billing_provider)
    base_url = settings.base_url.rstrip("/")
    reservation = await _checkout_attempt(
        session,
        organization_id=organization_id,
        price=price,
        admin_id=admin.id,
        idempotency_key=payload.idempotency_key,
        terms_version=settings.billing_terms_version,
        privacy_version=settings.billing_privacy_version,
        terms_sha256=settings.billing_terms_sha256,
        privacy_sha256=settings.billing_privacy_sha256,
    )
    attempt = reservation.attempt
    if reservation.abandoned_attempt_id is not None:
        record_audit_event(
            session,
            request,
            admin,
            action="billing.checkout_pending_abandoned",
            target_type="checkout_attempt",
            target_id=reservation.abandoned_attempt_id,
            organization_id=organization_id,
            details={"age_seconds": reservation.abandoned_age_seconds},
        )
        await session.commit()
    if reservation.recovered_pending:
        # Persist the recovery lease and its evidence before external I/O. A
        # crash can delay another lost-key recovery, but never permanently lock
        # the organization or create a provider request with a different key.
        record_audit_event(
            session,
            request,
            admin,
            action="billing.checkout_pending_recovered",
            target_type="checkout_attempt",
            target_id=attempt.id,
            organization_id=organization_id,
            details={
                "age_seconds": reservation.recovered_age_seconds,
                "original_requester_user_id": attempt.requested_by_user_id,
            },
        )
        await session.commit()
    if attempt.status == "created":
        if attempt.hosted_url is None or attempt.provider_session_id is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Checkout attempt is inconsistent")
        if attempt.expires_at is not None and _as_utc(attempt.expires_at) <= datetime.now(UTC):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Checkout session expired; create a new request with a new idempotency key",
            )
        try:
            stored = validate_hosted_session(
                HostedSession(
                    attempt.provider_session_id,
                    attempt.hosted_url,
                    attempt.expires_at,
                ),
                provider=settings.billing_provider,
                surface="checkout",
            )
        except BillingProviderError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Checkout attempt is inconsistent"
            ) from exc
        return HostedSessionOut(
            url=stored.url,
            expires_at=_as_utc(stored.expires_at) if stored.expires_at is not None else None,
        )
    requester_email = admin.email
    if attempt.requested_by_user_id != admin.id:
        stored_requester_email = await session.scalar(
            select(User.email)
            .where(User.id == attempt.requested_by_user_id)
            .execution_options(skip_org_filter=True)
        )
        if stored_requester_email is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Checkout attempt is inconsistent")
        requester_email = stored_requester_email
    try:
        hosted = validate_hosted_session(
            await provider.create_checkout(
                CheckoutRequest(
                    provider_price_id=price.provider_price_id,
                    organization_reference=str(organization_id),
                    customer_id=customer.provider_customer_id if customer is not None else None,
                    customer_email=requester_email if customer is None else None,
                    success_url=f"{base_url}/billing?checkout=success",
                    cancel_url=f"{base_url}/billing?checkout=cancelled",
                    idempotency_key=f"checkout:{organization_id}:{attempt.idempotency_key}",
                    terms_version=settings.billing_terms_version,
                    privacy_version=settings.billing_privacy_version,
                    terms_sha256=settings.billing_terms_sha256,
                    privacy_sha256=settings.billing_privacy_sha256,
                    consented_by_user_id=attempt.requested_by_user_id,
                )
            ),
            provider=settings.billing_provider,
            surface="checkout",
        )
    except BillingProviderError as exc:
        attempt.status = "failed"
        attempt.active_marker = None
        attempt.last_error_code = type(exc).__name__[:80]
        await session.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Billing provider is unavailable") from exc
    attempt.status = "created"
    attempt.active_marker = True
    attempt.provider_session_id = hosted.provider_session_id
    attempt.hosted_url = hosted.url
    attempt.expires_at = hosted.expires_at
    attempt.last_error_code = None
    record_audit_event(
        session,
        request,
        admin,
        action="billing.checkout_created",
        target_type="billing_price",
        target_id=price.id,
        organization_id=organization_id,
        details={
            "provider": settings.billing_provider,
            "price_version": price.version,
            "terms_version": settings.billing_terms_version,
            "privacy_version": settings.billing_privacy_version,
            "terms_sha256": settings.billing_terms_sha256,
            "privacy_sha256": settings.billing_privacy_sha256,
            "recovered_pending": reservation.recovered_pending,
            "original_requester_user_id": attempt.requested_by_user_id,
        },
    )
    # The durable provider result and its consent/audit evidence are one local
    # transaction. If this commit fails, the already-persisted pending attempt
    # remains retryable and the provider receives the same idempotency key.
    await session.commit()
    return HostedSessionOut(url=hosted.url, expires_at=hosted.expires_at)


@router.post("/portal", response_model=HostedSessionOut)
async def create_portal(
    payload: PortalCreate,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    provider: BillingProviderDep,
    admin: AdminUser,
    _: StepUpUser,
    organization_id: ExplicitOrgContext,
) -> HostedSessionOut:
    _require_provider(settings, provider)
    customer = await _customer_for_org(session, organization_id, settings.billing_provider)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Billing customer does not exist")
    try:
        hosted = validate_hosted_session(
            await provider.create_portal(
                PortalRequest(
                    customer_id=customer.provider_customer_id,
                    return_url=f"{settings.base_url.rstrip('/')}/billing",
                    idempotency_key=f"portal:{organization_id}:{payload.idempotency_key}",
                )
            ),
            provider=settings.billing_provider,
            surface="portal",
        )
    except BillingProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Billing provider is unavailable") from exc
    record_audit_event(
        session,
        request,
        admin,
        action="billing.portal_created",
        target_type="billing_customer",
        target_id=customer.id,
        organization_id=organization_id,
        details={"provider": settings.billing_provider},
    )
    return HostedSessionOut(url=hosted.url, expires_at=hosted.expires_at)


@router.post(
    "/webhooks/{provider_name}",
    response_model=WebhookAcceptedOut,
    include_in_schema=False,
)
async def receive_webhook(
    provider_name: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    provider: BillingProviderDep,
) -> WebhookAcceptedOut:
    if (
        not settings.billing_provider_configured
        or provider_name != settings.billing_provider
        or provider.provider_name != settings.billing_provider
    ):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing webhook is disabled")
    signatures = request.headers.getlist("stripe-signature")
    if provider_name == "stripe" and len(signatures) != 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook verification failed")
    raw_body = await _read_raw_body(request, settings.billing_webhook_max_body_bytes)
    try:
        verified = provider.verify_webhook(raw_body, request.headers)
    except WebhookVerificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook verification failed") from exc
    if verified.livemode != settings.stripe_livemode:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Webhook mode does not match configuration",
        )
    if provider_name == "stripe" and verified.api_version != settings.stripe_api_version:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Webhook API version does not match configuration",
        )
    try:
        result = await ingest_provider_event(
            session,
            verified,
            grace_days=settings.billing_past_due_grace_days,
            provider_client=provider,
        )
    except BillingProjectionError as exc:
        logger.error(
            "Billing projection failed provider=%s event_id=%s type=%s",
            verified.provider,
            verified.event_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Webhook processing failed"
        ) from exc
    return WebhookAcceptedOut(duplicate=result.duplicate)


@router.get("/prices", response_model=list[BillingPriceOut])
async def list_billing_prices(
    session: SessionDep, _: InstanceSuperadminUser
) -> list[BillingPriceOut]:
    rows = (
        await session.execute(
            select(BillingPrice).order_by(
                BillingPrice.provider, BillingPrice.plan_id, BillingPrice.version.desc()
            )
        )
    ).scalars()
    return [BillingPriceOut.model_validate(row) for row in rows]


@router.post("/prices", response_model=BillingPriceOut, status_code=status.HTTP_201_CREATED)
async def create_billing_price(
    payload: BillingPriceCreate,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    provider: BillingProviderDep,
    admin: InstanceSuperadminUser,
    _: StepUpUser,
) -> BillingPriceOut:
    plan = await session.get(Plan, payload.plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    if payload.currency.upper() != plan.currency.upper():
        raise HTTPException(status.HTTP_409_CONFLICT, "Billing price currency must match the plan")
    if payload.provider != settings.billing_provider or provider.provider_name != payload.provider:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing provider is unavailable")
    try:
        provider_price = await provider.get_price(payload.provider_price_id)
    except BillingProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Billing provider is unavailable") from exc
    _require_matching_price(
        provider_price,
        unit_amount_minor=payload.unit_amount_minor,
        currency=payload.currency,
        recurring_interval=payload.recurring_interval,
        interval_count=payload.interval_count,
    )
    # Provider I/O happens before taking the database lock. Re-read the plan
    # under the shared contract lock afterwards so a concurrent plan edit either
    # completes first and is observed here, or waits until this price is visible.
    plan = await lock_plan_contract(session, payload.plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    if payload.currency.upper() != plan.currency.upper():
        raise HTTPException(status.HTTP_409_CONFLICT, "Billing price currency must match the plan")
    duplicate = (
        await session.execute(
            select(BillingPrice.id).where(
                BillingPrice.provider == payload.provider,
                BillingPrice.provider_price_id == payload.provider_price_id,
            )
        )
    ).first()
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Provider price is already registered")
    previous = (
        (
            await session.execute(
                select(BillingPrice).where(
                    BillingPrice.plan_id == payload.plan_id,
                    BillingPrice.provider == payload.provider,
                    BillingPrice.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now(UTC)
    for price in previous:
        price.is_active = False
        price.retired_at = now
    version = (
        await session.execute(
            select(func.max(BillingPrice.version)).where(
                BillingPrice.plan_id == payload.plan_id,
                BillingPrice.provider == payload.provider,
            )
        )
    ).scalar_one_or_none()
    price = BillingPrice(
        **payload.model_dump(exclude={"currency"}),
        currency=payload.currency.upper(),
        version=(version or 0) + 1,
        is_active=True,
    )
    session.add(price)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Billing price is already registered or conflicts with another price version",
        ) from exc
    record_audit_event(
        session,
        request,
        admin,
        action="billing.price_version_created",
        target_type="billing_price",
        target_id=price.id,
        target_label=price.provider_price_id,
        organization_id=None,
        details={
            "provider": price.provider,
            "plan_id": price.plan_id,
            "version": price.version,
            "amount_minor": price.unit_amount_minor,
            "currency": price.currency,
        },
    )
    return BillingPriceOut.model_validate(price)


@router.post("/reconcile/{organization_id}", response_model=ReconciliationOut)
async def reconcile_billing_customer(
    organization_id: int,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    provider: BillingProviderDep,
    admin: SuperadminUser,
    _: StepUpUser,
    acting_organization_id: ExplicitOrgContext,
) -> ReconciliationOut:
    if acting_organization_id != organization_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Exit the current organization before reconciling a different tenant",
        )
    if (
        not settings.billing_provider_configured
        or provider.provider_name != settings.billing_provider
    ):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing is not configured")
    customer = await _customer_for_org(session, organization_id, settings.billing_provider)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Billing customer does not exist")
    try:
        result = await reconcile_customer(
            session,
            provider,
            customer,
            grace_days=settings.billing_past_due_grace_days,
        )
    except BillingProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Billing provider is unavailable") from exc
    record_audit_event(
        session,
        request,
        admin,
        action="billing.reconciled",
        target_type="billing_customer",
        target_id=customer.id,
        organization_id=organization_id,
        details={
            "provider": settings.billing_provider,
            "subscriptions_seen": result.subscriptions_seen,
            "subscriptions_updated": result.subscriptions_updated,
        },
    )
    return ReconciliationOut(
        organization_id=organization_id,
        subscriptions_seen=result.subscriptions_seen,
        subscriptions_updated=result.subscriptions_updated,
    )


async def _customer_for_org(
    session: AsyncSession, organization_id: int, provider: str
) -> BillingCustomer | None:
    if provider == "disabled":
        return None
    return (
        await session.execute(
            select(BillingCustomer).where(
                BillingCustomer.organization_id == organization_id,
                BillingCustomer.provider == provider,
            )
        )
    ).scalar_one_or_none()


def _require_self_serve(settings: Settings, provider: BillingProvider) -> None:
    if not settings.billing_self_serve_ready or provider.provider_name != settings.billing_provider:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Self-serve billing is disabled")


def _require_provider(settings: Settings, provider: BillingProvider) -> None:
    if (
        not settings.billing_provider_configured
        or provider.provider_name != settings.billing_provider
    ):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing is not configured")


async def _verify_provider_price(provider: BillingProvider, price: BillingPrice) -> None:
    try:
        provider_price = await provider.get_price(price.provider_price_id)
    except BillingProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Billing provider is unavailable") from exc
    _require_matching_price(
        provider_price,
        unit_amount_minor=price.unit_amount_minor,
        currency=price.currency,
        recurring_interval=price.recurring_interval,
        interval_count=price.interval_count,
    )


def _require_matching_price(
    provider_price: ProviderPrice,
    *,
    unit_amount_minor: int,
    currency: str,
    recurring_interval: str,
    interval_count: int,
) -> None:
    matches = (
        provider_price.active
        and provider_price.product_active
        and provider_price.unit_amount_minor == unit_amount_minor
        and provider_price.currency.upper() == currency.upper()
        and provider_price.recurring_interval == recurring_interval
        and provider_price.interval_count == interval_count
    )
    if not matches:
        raise HTTPException(status.HTTP_409_CONFLICT, "Provider price does not match the catalog")


async def _checkout_attempt(
    session: AsyncSession,
    *,
    organization_id: int,
    price: BillingPrice,
    admin_id: int,
    idempotency_key: str,
    terms_version: str,
    privacy_version: str,
    terms_sha256: str,
    privacy_sha256: str,
) -> _CheckoutReservation:
    now = datetime.now(UTC)
    attempt = (
        await session.execute(
            select(CheckoutAttempt).where(
                CheckoutAttempt.organization_id == organization_id,
                CheckoutAttempt.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if attempt is not None and not _checkout_contract_matches(
        attempt,
        price_id=price.id,
        admin_id=admin_id,
        terms_version=terms_version,
        privacy_version=privacy_version,
        terms_sha256=terms_sha256,
        privacy_sha256=privacy_sha256,
        require_requester=True,
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Idempotency key was already used for a different checkout request",
        )
    abandoned_attempt_id: int | None = None
    abandoned_age_seconds: int | None = None
    if attempt is None:
        active_attempt = (
            await session.execute(
                select(CheckoutAttempt)
                .where(
                    CheckoutAttempt.organization_id == organization_id,
                    CheckoutAttempt.active_marker.is_(True),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if active_attempt is not None:
            age = now - _as_utc(active_attempt.updated_at or active_attempt.created_at)
            expired = active_attempt.status == "created" and (
                (
                    active_attempt.expires_at is not None
                    and _as_utc(active_attempt.expires_at) <= now
                )
                or (active_attempt.expires_at is None and age >= _CHECKOUT_PENDING_ABANDON_AFTER)
            )
            if expired:
                active_attempt.status = "expired"
                active_attempt.active_marker = None
                await session.commit()
            elif (
                active_attempt.status == "pending"
                and age >= _CHECKOUT_PENDING_RECOVERY_AFTER
                and _checkout_contract_matches(
                    active_attempt,
                    price_id=price.id,
                    admin_id=admin_id,
                    terms_version=terms_version,
                    privacy_version=privacy_version,
                    terms_sha256=terms_sha256,
                    privacy_sha256=privacy_sha256,
                    require_requester=False,
                )
            ):
                active_attempt.updated_at = now
                return _CheckoutReservation(
                    active_attempt,
                    recovered_pending=True,
                    recovered_age_seconds=max(0, int(age.total_seconds())),
                )
            elif active_attempt.status == "pending" and age >= _CHECKOUT_PENDING_ABANDON_AFTER:
                active_attempt.status = "abandoned"
                active_attempt.active_marker = None
                abandoned_attempt_id = active_attempt.id
                abandoned_age_seconds = max(0, int(age.total_seconds()))
                await session.commit()
            else:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "An unfinished checkout attempt already exists",
                ) from None
        attempt = CheckoutAttempt(
            organization_id=organization_id,
            billing_price_id=price.id,
            requested_by_user_id=admin_id,
            idempotency_key=idempotency_key,
            terms_version=terms_version,
            privacy_version=privacy_version,
            terms_sha256=terms_sha256,
            privacy_sha256=privacy_sha256,
            status="pending",
            active_marker=True,
        )
        session.add(attempt)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            attempt = (
                await session.execute(
                    select(CheckoutAttempt).where(
                        CheckoutAttempt.organization_id == organization_id,
                        CheckoutAttempt.idempotency_key == idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if attempt is None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "An unfinished checkout attempt already exists",
                ) from None
    elif attempt.status == "failed":
        attempt.status = "pending"
        attempt.active_marker = True
        attempt.last_error_code = None
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "An unfinished checkout attempt already exists",
            ) from exc
    elif attempt.status not in {"pending", "created"}:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Checkout attempt is terminal; create a new request with a new idempotency key",
        )
    if not _checkout_contract_matches(
        attempt,
        price_id=price.id,
        admin_id=admin_id,
        terms_version=terms_version,
        privacy_version=privacy_version,
        terms_sha256=terms_sha256,
        privacy_sha256=privacy_sha256,
        require_requester=True,
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Idempotency key was already used for a different checkout request",
        )
    return _CheckoutReservation(
        attempt,
        abandoned_attempt_id=abandoned_attempt_id,
        abandoned_age_seconds=abandoned_age_seconds,
    )


def _checkout_contract_matches(
    attempt: CheckoutAttempt,
    *,
    price_id: int,
    admin_id: int,
    terms_version: str,
    privacy_version: str,
    terms_sha256: str,
    privacy_sha256: str,
    require_requester: bool,
) -> bool:
    return (
        attempt.billing_price_id == price_id
        and (not require_requester or attempt.requested_by_user_id == admin_id)
        and attempt.terms_version == terms_version
        and attempt.privacy_version == privacy_version
        and attempt.terms_sha256 == terms_sha256
        and attempt.privacy_sha256 == privacy_sha256
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _read_raw_body(request: Request, maximum: int) -> bytes:
    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Expected application/json")
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid content length") from exc
        if declared < 0 or declared > maximum:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Webhook payload is too large")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > maximum:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Webhook payload is too large")
        chunks.append(chunk)
    return b"".join(chunks)
