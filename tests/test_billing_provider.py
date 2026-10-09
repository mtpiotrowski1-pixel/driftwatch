from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest

from driftwatch.billing.provider import (
    BillingProviderError,
    CheckoutRequest,
    HostedSession,
    SubscriptionSnapshot,
    WebhookVerificationError,
    subscription_access_decision,
    validate_hosted_session,
)
from driftwatch.billing.stripe import StripeBillingProvider

_STRIPE_API_VERSION = "2025-06-30.basil"


def _signed_stripe_payload(
    payload: dict[str, object],
    *,
    secret: str,
    timestamp: int,
) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(
        secret.encode("utf-8"),
        str(timestamp).encode("ascii") + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    return raw, {"stripe-signature": f"t={timestamp},v1={signature}"}


@pytest.mark.parametrize("status", ["paused", "incomplete", "incomplete_expired", "unknown"])
def test_unknown_and_non_entitled_statuses_fail_closed(status: str) -> None:
    decision = subscription_access_decision(
        status,
        now=datetime(2026, 1, 1, tzinfo=UTC),
        past_due_since=None,
        grace_days=7,
        trial_end=None,
        current_period_end=None,
    )

    assert decision.entitled is False
    assert decision.suspend is True


def test_trial_and_active_period_must_be_bounded_and_unexpired() -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)

    for status, trial_end, period_end in (
        ("trialing", now, None),
        ("trialing", None, None),
        ("active", None, now),
        ("active", None, None),
    ):
        decision = subscription_access_decision(
            status,
            now=now,
            past_due_since=None,
            grace_days=7,
            trial_end=trial_end,
            current_period_end=period_end,
        )
        assert decision.entitled is False
        assert decision.suspend is True

    trial = subscription_access_decision(
        "trialing",
        now=now,
        past_due_since=None,
        grace_days=7,
        trial_end=now + timedelta(days=1),
    )
    assert trial.entitled is True


@pytest.mark.parametrize(
    ("surface", "url"),
    [
        ("checkout", "https://billing.stripe.com/p/session/test"),
        ("checkout", "https://checkout.stripe.com.evil.test/c/pay/test"),
        ("portal", "https://billing.stripe.com:444/p/session/test"),
        ("portal", "https://user@billing.stripe.com/p/session/test"),
    ],
)
def test_hosted_session_destinations_are_surface_specific_and_pinned(
    surface: str,
    url: str,
) -> None:
    with pytest.raises(BillingProviderError, match="invalid hosted URL"):
        validate_hosted_session(
            HostedSession("session", url),
            provider="stripe",
            surface=surface,  # type: ignore[arg-type]
        )


def test_expected_stripe_hosted_session_is_accepted() -> None:
    session = HostedSession("session", "https://checkout.stripe.com/c/pay/test")
    assert validate_hosted_session(session, provider="stripe", surface="checkout") is session


@pytest.mark.asyncio
async def test_checkout_metadata_binds_legal_document_fingerprints() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        form = parse_qs((await request.aread()).decode("utf-8"))
        assert form["metadata[driftwatch_terms_sha256]"] == ["a" * 64]
        assert form["metadata[driftwatch_privacy_sha256]"] == ["b" * 64]
        return httpx.Response(
            200,
            json={
                "id": "cs_legal",
                "url": "https://checkout.stripe.com/c/pay/cs_legal",
                "expires_at": 1_800_000_000,
            },
        )

    provider = StripeBillingProvider(
        api_key="sk_test_1234567890",
        webhook_secret="whsec_1234567890",
        api_version="2025-06-30.basil",
        transport=httpx.MockTransport(handler),
    )
    try:
        hosted = await provider.create_checkout(
            CheckoutRequest(
                provider_price_id="price_paid",
                organization_reference="7",
                customer_id=None,
                customer_email="owner@example.com",
                success_url="https://app.example.test/billing?checkout=success",
                cancel_url="https://app.example.test/billing?checkout=cancelled",
                idempotency_key="checkout:7:test",
                terms_version="terms-2026-01",
                privacy_version="privacy-2026-01",
                terms_sha256="a" * 64,
                privacy_sha256="b" * 64,
                consented_by_user_id=11,
            )
        )
    finally:
        await provider.aclose()

    assert hosted.provider_session_id == "cs_legal"


@pytest.mark.asyncio
async def test_stripe_price_is_read_and_normalized_from_provider() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/prices/price_monthly"
        assert request.url.params["expand[]"] == "product"
        return httpx.Response(
            200,
            json={
                "id": "price_monthly",
                "active": True,
                "currency": "usd",
                "unit_amount": 1900,
                "type": "recurring",
                "recurring": {"interval": "month", "interval_count": 1},
                "product": {"id": "prod_1", "active": True},
            },
        )

    provider = StripeBillingProvider(
        api_key="sk_test_1234567890",
        webhook_secret="whsec_1234567890",
        api_version="2025-06-30.basil",
        transport=httpx.MockTransport(handler),
    )
    try:
        price = await provider.get_price("price_monthly")
    finally:
        await provider.aclose()

    assert price.unit_amount_minor == 1900
    assert price.currency == "USD"
    assert price.active is True
    assert price.product_active is True


@pytest.mark.asyncio
async def test_stripe_rejects_non_recurring_provider_price() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps(
                {
                    "id": "price_once",
                    "active": True,
                    "currency": "usd",
                    "unit_amount": 100,
                    "type": "one_time",
                    "product": {"active": True},
                }
            ),
        )

    provider = StripeBillingProvider(
        api_key="sk_test_1234567890",
        webhook_secret="whsec_1234567890",
        api_version="2025-06-30.basil",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(BillingProviderError, match="not recurring"):
            await provider.get_price("price_once")
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_signed_basil_subscription_uses_conservative_item_period() -> None:
    secret = "whsec_realistic_signed_payload"
    created = 1_767_225_600
    payload: dict[str, object] = {
        "id": "evt_basil_subscription",
        "object": "event",
        "api_version": _STRIPE_API_VERSION,
        "created": created,
        "livemode": False,
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_basil",
                "object": "subscription",
                "customer": "cus_basil",
                "status": "active",
                "metadata": {"driftwatch_org_id": "17"},
                # Basil no longer defines the subscription period here. These
                # misleading legacy fields must not influence the projection.
                "current_period_start": created - 90 * 86_400,
                "current_period_end": created + 365 * 86_400,
                "items": {
                    "object": "list",
                    "data": [
                        {
                            "id": "si_monthly",
                            "object": "subscription_item",
                            "price": "price_monthly",
                            "quantity": 1,
                            "current_period_start": created - 86_400,
                            "current_period_end": created + 30 * 86_400,
                        },
                        {
                            "id": "si_addon",
                            "object": "subscription_item",
                            "price": {"id": "price_addon"},
                            "quantity": 2,
                            "current_period_start": created,
                            "current_period_end": created + 29 * 86_400,
                        },
                    ],
                },
                "trial_end": None,
                "cancel_at_period_end": False,
                "canceled_at": None,
            }
        },
    }
    raw, headers = _signed_stripe_payload(payload, secret=secret, timestamp=created)
    provider = StripeBillingProvider(
        api_key="sk_test_1234567890",
        webhook_secret=secret,
        api_version=_STRIPE_API_VERSION,
    )
    try:
        event = provider.verify_webhook(
            raw,
            headers,
            now=datetime.fromtimestamp(created, tz=UTC),
        )
    finally:
        await provider.aclose()

    assert isinstance(event.resource, SubscriptionSnapshot)
    assert event.resource.current_period_start == datetime.fromtimestamp(created, tz=UTC)
    assert event.resource.current_period_end == datetime.fromtimestamp(
        created + 29 * 86_400,
        tz=UTC,
    )


@pytest.mark.asyncio
async def test_signed_webhook_rejects_a_different_stripe_api_version() -> None:
    secret = "whsec_realistic_signed_payload"
    created = 1_767_225_600
    payload: dict[str, object] = {
        "id": "evt_wrong_version",
        "api_version": "2025-03-31.basil",
        "created": created,
        "livemode": False,
        "type": "unsupported.event",
        "data": {"object": {"id": "unsupported"}},
    }
    raw, headers = _signed_stripe_payload(payload, secret=secret, timestamp=created)
    provider = StripeBillingProvider(
        api_key="sk_test_1234567890",
        webhook_secret=secret,
        api_version=_STRIPE_API_VERSION,
    )
    try:
        with pytest.raises(WebhookVerificationError, match="verification failed"):
            provider.verify_webhook(
                raw,
                headers,
                now=datetime.fromtimestamp(created, tz=UTC),
            )
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_signed_subscription_rejects_truncated_embedded_items() -> None:
    secret = "whsec_realistic_signed_payload"
    created = 1_767_225_600
    payload: dict[str, object] = {
        "id": "evt_truncated_items",
        "api_version": _STRIPE_API_VERSION,
        "created": created,
        "livemode": False,
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_truncated",
                "customer": "cus_truncated",
                "status": "active",
                "metadata": {},
                "items": {
                    "data": [
                        {
                            "id": "si_visible",
                            "price": "price_visible",
                            "quantity": 1,
                            "current_period_start": created,
                            "current_period_end": created + 30 * 86_400,
                        }
                    ],
                    "has_more": True,
                },
                "trial_end": None,
                "cancel_at_period_end": False,
                "canceled_at": None,
            }
        },
    }
    raw, headers = _signed_stripe_payload(payload, secret=secret, timestamp=created)
    provider = StripeBillingProvider(
        api_key="sk_test_1234567890",
        webhook_secret=secret,
        api_version=_STRIPE_API_VERSION,
    )
    try:
        with pytest.raises(WebhookVerificationError, match="verification failed"):
            provider.verify_webhook(
                raw,
                headers,
                now=datetime.fromtimestamp(created, tz=UTC),
            )
    finally:
        await provider.aclose()
