"""Stable billing-provider boundary and subscription access policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from urllib.parse import urlsplit


class BillingProviderError(Exception):
    """A provider call failed without exposing upstream response details."""


class BillingUnavailable(BillingProviderError):
    """Billing is intentionally disabled or incompletely configured."""


class WebhookVerificationError(BillingProviderError):
    """A webhook signature or normalized event envelope is invalid."""


@dataclass(frozen=True, slots=True)
class CheckoutRequest:
    provider_price_id: str
    organization_reference: str
    customer_id: str | None
    customer_email: str | None
    success_url: str
    cancel_url: str
    idempotency_key: str
    terms_version: str
    privacy_version: str
    terms_sha256: str
    privacy_sha256: str
    consented_by_user_id: int


@dataclass(frozen=True, slots=True)
class PortalRequest:
    customer_id: str
    return_url: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class HostedSession:
    provider_session_id: str
    url: str
    expires_at: datetime | None = None


type HostedSurface = Literal["checkout", "portal"]

_TRUSTED_HOSTED_SESSION_HOSTS: Mapping[tuple[str, HostedSurface], frozenset[str]] = {
    ("stripe", "checkout"): frozenset({"checkout.stripe.com"}),
    ("stripe", "portal"): frozenset({"billing.stripe.com"}),
}


def validate_hosted_session(
    session: HostedSession,
    *,
    provider: str,
    surface: HostedSurface,
) -> HostedSession:
    """Fail closed before returning a provider-controlled browser destination."""
    allowed_hosts = _TRUSTED_HOSTED_SESSION_HOSTS.get((provider, surface))
    if allowed_hosts is None:
        raise BillingProviderError("Billing provider has no trusted hosted-session policy")
    url = session.url
    if not url or len(url) > 2_048 or any(ord(character) < 32 for character in url):
        raise BillingProviderError("Billing provider returned an invalid hosted URL")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise BillingProviderError("Billing provider returned an invalid hosted URL") from exc
    if (
        parts.scheme != "https"
        or (parts.hostname or "").lower() not in allowed_hosts
        or parts.username is not None
        or parts.password is not None
        or port not in {None, 443}
    ):
        raise BillingProviderError("Billing provider returned an invalid hosted URL")
    return session


@dataclass(frozen=True, slots=True)
class ProviderPrice:
    provider_price_id: str
    unit_amount_minor: int
    currency: str
    recurring_interval: str
    interval_count: int
    active: bool
    product_active: bool


@dataclass(frozen=True, slots=True)
class SubscriptionLine:
    provider_item_id: str
    provider_price_id: str
    quantity: int


@dataclass(frozen=True, slots=True)
class SubscriptionSnapshot:
    provider_subscription_id: str
    provider_customer_id: str
    status: str
    organization_reference: str | None
    items: tuple[SubscriptionLine, ...]
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    trial_end: datetime | None = None
    cancel_at_period_end: bool = False
    canceled_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CheckoutSnapshot:
    provider_checkout_id: str
    provider_customer_id: str
    provider_subscription_id: str | None
    organization_reference: str | None
    terms_version: str | None
    privacy_version: str | None
    terms_sha256: str | None
    privacy_sha256: str | None
    consented_by_user_id: int | None


@dataclass(frozen=True, slots=True)
class InvoiceSnapshot:
    provider_invoice_id: str
    provider_customer_id: str
    provider_subscription_id: str | None
    invoice_number: str | None
    status: str
    currency: str
    amount_due_minor: int
    amount_paid_minor: int
    provider_created_at: datetime | None = None
    due_at: datetime | None = None
    paid_at: datetime | None = None


type BillingResource = SubscriptionSnapshot | CheckoutSnapshot | InvoiceSnapshot | None


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    provider: str
    event_id: str
    event_type: str
    occurred_at: datetime
    received_at: datetime
    livemode: bool
    api_version: str | None
    payload_sha256: str
    resource: BillingResource

    @property
    def resource_id(self) -> str | None:
        resource = self.resource
        if isinstance(resource, SubscriptionSnapshot):
            return resource.provider_subscription_id
        if isinstance(resource, CheckoutSnapshot):
            return resource.provider_checkout_id
        if isinstance(resource, InvoiceSnapshot):
            return resource.provider_invoice_id
        return None

    def ledger_data(self) -> dict[str, object]:
        """Return only fields needed to retry a projection, never a raw provider payload."""
        resource = self.resource
        if isinstance(resource, SubscriptionSnapshot):
            return {
                "kind": "subscription",
                "subscription_id": resource.provider_subscription_id,
                "customer_id": resource.provider_customer_id,
                "status": resource.status,
                "organization_reference": resource.organization_reference,
                "items": [
                    {
                        "item_id": item.provider_item_id,
                        "price_id": item.provider_price_id,
                        "quantity": item.quantity,
                    }
                    for item in resource.items
                ],
                "current_period_start": _iso(resource.current_period_start),
                "current_period_end": _iso(resource.current_period_end),
                "trial_end": _iso(resource.trial_end),
                "cancel_at_period_end": resource.cancel_at_period_end,
                "canceled_at": _iso(resource.canceled_at),
            }
        if isinstance(resource, CheckoutSnapshot):
            return {
                "kind": "checkout",
                "checkout_id": resource.provider_checkout_id,
                "customer_id": resource.provider_customer_id,
                "subscription_id": resource.provider_subscription_id,
                "organization_reference": resource.organization_reference,
                "terms_version": resource.terms_version,
                "privacy_version": resource.privacy_version,
                "terms_sha256": resource.terms_sha256,
                "privacy_sha256": resource.privacy_sha256,
                "consented_by_user_id": resource.consented_by_user_id,
            }
        if isinstance(resource, InvoiceSnapshot):
            return {
                "kind": "invoice",
                "invoice_id": resource.provider_invoice_id,
                "customer_id": resource.provider_customer_id,
                "subscription_id": resource.provider_subscription_id,
                "invoice_number": resource.invoice_number,
                "status": resource.status,
                "currency": resource.currency,
                "amount_due_minor": resource.amount_due_minor,
                "amount_paid_minor": resource.amount_paid_minor,
                "provider_created_at": _iso(resource.provider_created_at),
                "due_at": _iso(resource.due_at),
                "paid_at": _iso(resource.paid_at),
            }
        return {"kind": "unsupported"}


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    customer_id: int
    subscriptions_seen: int
    subscriptions_updated: int
    ignored_out_of_order: int = 0


class BillingProvider(Protocol):
    provider_name: str

    async def create_checkout(self, request: CheckoutRequest) -> HostedSession: ...

    async def create_portal(self, request: PortalRequest) -> HostedSession: ...

    async def get_price(self, provider_price_id: str) -> ProviderPrice: ...

    def verify_webhook(
        self,
        raw_body: bytes,
        headers: Mapping[str, str],
        *,
        now: datetime | None = None,
    ) -> ProviderEvent: ...

    async def list_subscriptions(self, customer_id: str) -> Sequence[SubscriptionSnapshot]: ...

    async def aclose(self) -> None: ...


class DisabledBillingProvider:
    provider_name = "disabled"

    async def create_checkout(self, request: CheckoutRequest) -> HostedSession:
        raise BillingUnavailable("Billing is not available")

    async def create_portal(self, request: PortalRequest) -> HostedSession:
        raise BillingUnavailable("Billing is not available")

    async def get_price(self, provider_price_id: str) -> ProviderPrice:
        raise BillingUnavailable("Billing is not available")

    def verify_webhook(
        self,
        raw_body: bytes,
        headers: Mapping[str, str],
        *,
        now: datetime | None = None,
    ) -> ProviderEvent:
        raise BillingUnavailable("Billing is not available")

    async def list_subscriptions(self, customer_id: str) -> Sequence[SubscriptionSnapshot]:
        raise BillingUnavailable("Billing is not available")

    async def aclose(self) -> None:
        return None


# Explicit product policy. `past_due` retains access only for a bounded grace
# window; `unpaid` and `canceled` suspend immediately. Unknown/initial states do
# not grant paid access and fail closed by suspending provider-managed access.
SUBSCRIPTION_ACCESS_MATRIX: Mapping[str, str] = {
    "active": "grant",
    "trialing": "grant_until_trial_end",
    "past_due": "grant_during_bounded_grace_then_suspend",
    "unpaid": "revoke_and_suspend",
    "canceled": "revoke_and_suspend",
}


@dataclass(frozen=True, slots=True)
class SubscriptionAccessDecision:
    entitled: bool
    suspend: bool
    valid_until: datetime | None
    reason: str


def subscription_access_decision(
    status: str,
    *,
    now: datetime,
    past_due_since: datetime | None,
    grace_days: int,
    trial_end: datetime | None,
    current_period_end: datetime | None = None,
) -> SubscriptionAccessDecision:
    now = _as_utc(now)
    trial_end = _as_utc(trial_end) if trial_end is not None else None
    current_period_end = _as_utc(current_period_end) if current_period_end is not None else None
    past_due_since = _as_utc(past_due_since) if past_due_since is not None else None
    normalized = status.strip().lower()
    if normalized == "active":
        if current_period_end is None or now >= current_period_end:
            return SubscriptionAccessDecision(False, True, current_period_end, "period_expired")
        return SubscriptionAccessDecision(True, False, current_period_end, "subscription_active")
    if normalized == "trialing":
        if trial_end is None or now >= trial_end:
            return SubscriptionAccessDecision(False, True, trial_end, "trial_expired")
        return SubscriptionAccessDecision(True, False, trial_end, "subscription_trialing")
    if normalized == "past_due":
        grace_start = past_due_since or now
        grace_until = grace_start + timedelta(days=grace_days)
        within_grace = now < grace_until
        return SubscriptionAccessDecision(
            within_grace,
            not within_grace,
            grace_until,
            "payment_grace" if within_grace else "payment_grace_expired",
        )
    if normalized in {"unpaid", "canceled"}:
        return SubscriptionAccessDecision(False, True, None, f"subscription_{normalized}")
    return SubscriptionAccessDecision(False, True, None, f"subscription_{normalized or 'unknown'}")


def utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
