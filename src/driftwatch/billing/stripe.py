"""Stripe adapter using hosted surfaces only; no card data crosses Driftwatch."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, NoReturn

import httpx
from pydantic import SecretStr

from driftwatch.billing.provider import (
    BillingProviderError,
    BillingResource,
    CheckoutRequest,
    CheckoutSnapshot,
    HostedSession,
    HostedSurface,
    InvoiceSnapshot,
    PortalRequest,
    ProviderEvent,
    ProviderPrice,
    SubscriptionLine,
    SubscriptionSnapshot,
    WebhookVerificationError,
    utcnow,
    validate_hosted_session,
)

_MAX_PROVIDER_RESPONSE_BYTES = 1_048_576
_MAX_PAGES = 20
_SUBSCRIPTION_EVENTS = frozenset(
    {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.paused",
        "customer.subscription.resumed",
    }
)
_CHECKOUT_EVENTS = frozenset(
    {"checkout.session.completed", "checkout.session.async_payment_succeeded"}
)
_INVOICE_EVENTS = frozenset(
    {
        "invoice.created",
        "invoice.finalized",
        "invoice.paid",
        "invoice.payment_failed",
        "invoice.updated",
        "invoice.voided",
        "invoice.marked_uncollectible",
    }
)


class StripeBillingProvider:
    provider_name = "stripe"

    def __init__(
        self,
        *,
        api_key: str,
        webhook_secret: str,
        api_version: str,
        base_url: str = "https://api.stripe.com",
        timeout_seconds: float = 15.0,
        webhook_tolerance_seconds: int = 300,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._webhook_secret = SecretStr(webhook_secret)
        self._api_version = api_version
        self._tolerance_seconds = webhook_tolerance_seconds
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Stripe-Version": api_version,
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": "DriftwatchBilling/1.0",
            },
        )

    async def create_checkout(self, request: CheckoutRequest) -> HostedSession:
        data: dict[str, str] = {
            "mode": "subscription",
            "ui_mode": "hosted",
            "success_url": request.success_url,
            "cancel_url": request.cancel_url,
            "client_reference_id": request.organization_reference,
            "line_items[0][price]": request.provider_price_id,
            "line_items[0][quantity]": "1",
            "metadata[driftwatch_org_id]": request.organization_reference,
            "metadata[driftwatch_terms_version]": request.terms_version,
            "metadata[driftwatch_privacy_version]": request.privacy_version,
            "metadata[driftwatch_terms_sha256]": request.terms_sha256,
            "metadata[driftwatch_privacy_sha256]": request.privacy_sha256,
            "metadata[driftwatch_user_id]": str(request.consented_by_user_id),
            "subscription_data[metadata][driftwatch_org_id]": request.organization_reference,
        }
        if request.customer_id:
            data["customer"] = request.customer_id
        elif request.customer_email:
            data["customer_email"] = request.customer_email
        payload = await self._request_json(
            "POST",
            "/v1/checkout/sessions",
            data=data,
            idempotency_key=request.idempotency_key,
        )
        return _hosted_session(payload, provider=self.provider_name, surface="checkout")

    async def create_portal(self, request: PortalRequest) -> HostedSession:
        payload = await self._request_json(
            "POST",
            "/v1/billing_portal/sessions",
            data={"customer": request.customer_id, "return_url": request.return_url},
            idempotency_key=request.idempotency_key,
        )
        return _hosted_session(payload, provider=self.provider_name, surface="portal")

    async def get_price(self, provider_price_id: str) -> ProviderPrice:
        if not provider_price_id or len(provider_price_id) > 255:
            raise BillingProviderError("Billing price identifier is invalid")
        payload = await self._request_json(
            "GET",
            f"/v1/prices/{provider_price_id}",
            params={"expand[]": "product"},
        )
        return _provider_price(payload, expected_id=provider_price_id)

    def verify_webhook(
        self,
        raw_body: bytes,
        headers: Mapping[str, str],
        *,
        now: datetime | None = None,
    ) -> ProviderEvent:
        received_at = (now or utcnow()).astimezone(UTC)
        signature_header = _header(headers, "stripe-signature")
        timestamp, signatures = _parse_signature(signature_header)
        if abs(int(received_at.timestamp()) - timestamp) > self._tolerance_seconds:
            _invalid_webhook()
        signed = str(timestamp).encode("ascii") + b"." + raw_body
        expected = hmac.new(
            self._webhook_secret.get_secret_value().encode("utf-8"),
            signed,
            hashlib.sha256,
        ).hexdigest()
        if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
            _invalid_webhook()
        try:
            envelope = json.loads(raw_body, parse_constant=_reject_json_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise WebhookVerificationError("Webhook verification failed") from exc
        if not isinstance(envelope, dict):
            _invalid_webhook()
        event_id = _required_text(envelope.get("id"), 255)
        event_type = _required_text(envelope.get("type"), 120)
        created = _required_timestamp(envelope.get("created"))
        livemode = envelope.get("livemode")
        if not isinstance(livemode, bool):
            _invalid_webhook()
        api_version = _optional_text(envelope.get("api_version"), 40)
        if api_version != self._api_version:
            _invalid_webhook()
        data = envelope.get("data")
        provider_object = data.get("object") if isinstance(data, dict) else None
        if not isinstance(provider_object, dict):
            _invalid_webhook()
        resource = _normalize_resource(event_type, provider_object)
        return ProviderEvent(
            provider=self.provider_name,
            event_id=event_id,
            event_type=event_type,
            occurred_at=created,
            received_at=received_at,
            livemode=livemode,
            api_version=api_version,
            payload_sha256=hashlib.sha256(raw_body).hexdigest(),
            resource=resource,
        )

    async def list_subscriptions(self, customer_id: str) -> Sequence[SubscriptionSnapshot]:
        subscriptions: list[SubscriptionSnapshot] = []
        starting_after: str | None = None
        for _ in range(_MAX_PAGES):
            params = {"customer": customer_id, "status": "all", "limit": "100"}
            if starting_after is not None:
                params["starting_after"] = starting_after
            payload = await self._request_json("GET", "/v1/subscriptions", params=params)
            raw_items = payload.get("data")
            if not isinstance(raw_items, list):
                raise BillingProviderError("Billing provider returned an invalid response")
            page: list[SubscriptionSnapshot] = []
            for item in raw_items:
                if not isinstance(item, dict):
                    raise BillingProviderError("Billing provider returned an invalid response")
                page.append(_subscription_snapshot(item))
            subscriptions.extend(page)
            if payload.get("has_more") is not True:
                return subscriptions
            if not page:
                raise BillingProviderError("Billing provider pagination did not advance")
            starting_after = page[-1].provider_subscription_id
        raise BillingProviderError("Billing provider pagination exceeded the safety limit")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        data: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        try:
            async with self._client.stream(
                method,
                path,
                data=data,
                params=params,
                headers=headers,
            ) as response:
                body = await _read_limited(response, _MAX_PROVIDER_RESPONSE_BYTES)
        except httpx.TimeoutException as exc:
            raise BillingProviderError("Billing provider timed out") from exc
        except httpx.HTTPError as exc:
            raise BillingProviderError("Billing provider is unavailable") from exc
        if not 200 <= response.status_code < 300:
            raise BillingProviderError("Billing provider rejected the request")
        try:
            payload = json.loads(body, parse_constant=_reject_json_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise BillingProviderError("Billing provider returned an invalid response") from exc
        if not isinstance(payload, dict):
            raise BillingProviderError("Billing provider returned an invalid response")
        return payload


async def _read_limited(response: httpx.Response, maximum: int) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > maximum:
                raise BillingProviderError("Billing provider response exceeded the limit")
        except ValueError as exc:
            raise BillingProviderError("Billing provider returned an invalid response") from exc
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > maximum:
            raise BillingProviderError("Billing provider response exceeded the limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _hosted_session(
    payload: Mapping[str, object],
    *,
    provider: str,
    surface: HostedSurface,
) -> HostedSession:
    session_id = _required_text(payload.get("id"), 255)
    url = _required_text(payload.get("url"), 2_048)
    expires_at = _optional_timestamp(payload.get("expires_at"))
    return validate_hosted_session(
        HostedSession(session_id, url, expires_at),
        provider=provider,
        surface=surface,
    )


def _provider_price(payload: Mapping[str, object], *, expected_id: str) -> ProviderPrice:
    price_id = _required_text(payload.get("id"), 255)
    if price_id != expected_id:
        raise BillingProviderError("Billing provider returned a mismatched price")
    unit_amount = payload.get("unit_amount")
    if not isinstance(unit_amount, int) or isinstance(unit_amount, bool) or unit_amount < 0:
        raise BillingProviderError("Billing provider returned an invalid price")
    if payload.get("type") != "recurring":
        raise BillingProviderError("Billing provider price is not recurring")
    recurring = payload.get("recurring")
    if not isinstance(recurring, dict):
        raise BillingProviderError("Billing provider returned an invalid price")
    interval = recurring.get("interval")
    interval_count = recurring.get("interval_count")
    if (
        interval not in {"day", "week", "month", "year"}
        or not isinstance(interval_count, int)
        or isinstance(interval_count, bool)
        or not 1 <= interval_count <= 36
    ):
        raise BillingProviderError("Billing provider returned an invalid price")
    product = payload.get("product")
    product_active = product.get("active") is True if isinstance(product, dict) else False
    return ProviderPrice(
        provider_price_id=price_id,
        unit_amount_minor=unit_amount,
        currency=_required_text(payload.get("currency"), 3).upper(),
        recurring_interval=interval,
        interval_count=interval_count,
        active=payload.get("active") is True,
        product_active=product_active,
    )


def _normalize_resource(event_type: str, value: Mapping[str, object]) -> BillingResource:
    if event_type in _SUBSCRIPTION_EVENTS:
        return _subscription_snapshot(value)
    if event_type in _CHECKOUT_EVENTS:
        return _checkout_snapshot(value)
    if event_type in _INVOICE_EVENTS:
        return _invoice_snapshot(value)
    return None


def _subscription_snapshot(value: Mapping[str, object]) -> SubscriptionSnapshot:
    subscription_id = _required_text(value.get("id"), 255)
    customer_id = _object_id(value.get("customer"))
    status = _required_text(value.get("status"), 32).lower()
    metadata = _metadata(value.get("metadata"))
    raw_items = value.get("items")
    raw_data = raw_items.get("data") if isinstance(raw_items, dict) else None
    raw_has_more = raw_items.get("has_more") if isinstance(raw_items, dict) else None
    if raw_has_more is not None and not isinstance(raw_has_more, bool):
        _invalid_webhook()
    if raw_has_more is True:
        # Embedded subscription items are a bounded partial list. Projecting a
        # truncated set could hide an unmapped or cross-plan item and grant the
        # wrong entitlement, so the caller must retry/reconcile a complete view.
        _invalid_webhook()
    if not isinstance(raw_data, list) or len(raw_data) > 100:
        _invalid_webhook()
    items: list[SubscriptionLine] = []
    item_period_starts: list[datetime] = []
    item_period_ends: list[datetime] = []
    complete_item_period = bool(raw_data)
    for raw_item in raw_data:
        if not isinstance(raw_item, dict):
            _invalid_webhook()
        price_id = _object_id(raw_item.get("price"))
        quantity = raw_item.get("quantity", 1)
        if (
            not isinstance(quantity, int)
            or isinstance(quantity, bool)
            or not 1 <= quantity <= 1_000_000
        ):
            _invalid_webhook()
        items.append(
            SubscriptionLine(
                provider_item_id=_required_text(raw_item.get("id"), 255),
                provider_price_id=price_id,
                quantity=quantity,
            )
        )
        item_period_start = _optional_timestamp(raw_item.get("current_period_start"))
        item_period_end = _optional_timestamp(raw_item.get("current_period_end"))
        if item_period_start is None or item_period_end is None:
            complete_item_period = False
        else:
            item_period_starts.append(item_period_start)
            item_period_ends.append(item_period_end)
    current_period_start = max(item_period_starts) if complete_item_period else None
    current_period_end = min(item_period_ends) if complete_item_period else None
    if (
        current_period_start is not None
        and current_period_end is not None
        and current_period_end <= current_period_start
    ):
        _invalid_webhook()
    return SubscriptionSnapshot(
        provider_subscription_id=subscription_id,
        provider_customer_id=customer_id,
        status=status,
        organization_reference=_optional_text(metadata.get("driftwatch_org_id"), 40),
        items=tuple(items),
        current_period_start=current_period_start,
        current_period_end=current_period_end,
        trial_end=_optional_timestamp(value.get("trial_end")),
        cancel_at_period_end=value.get("cancel_at_period_end") is True,
        canceled_at=_optional_timestamp(value.get("canceled_at")),
    )


def _checkout_snapshot(value: Mapping[str, object]) -> CheckoutSnapshot:
    metadata = _metadata(value.get("metadata"))
    raw_user_id = metadata.get("driftwatch_user_id")
    consented_by = _optional_positive_int(raw_user_id)
    reference = _optional_text(value.get("client_reference_id"), 40) or _optional_text(
        metadata.get("driftwatch_org_id"), 40
    )
    return CheckoutSnapshot(
        provider_checkout_id=_required_text(value.get("id"), 255),
        provider_customer_id=_object_id(value.get("customer")),
        provider_subscription_id=_optional_object_id(value.get("subscription")),
        organization_reference=reference,
        terms_version=_optional_text(metadata.get("driftwatch_terms_version"), 80),
        privacy_version=_optional_text(metadata.get("driftwatch_privacy_version"), 80),
        terms_sha256=_optional_sha256(metadata.get("driftwatch_terms_sha256")),
        privacy_sha256=_optional_sha256(metadata.get("driftwatch_privacy_sha256")),
        consented_by_user_id=consented_by,
    )


def _invoice_snapshot(value: Mapping[str, object]) -> InvoiceSnapshot | None:
    customer_id = _optional_object_id(value.get("customer"))
    if customer_id is None:
        return None
    subscription_id = _optional_object_id(value.get("subscription"))
    if subscription_id is None:
        parent = value.get("parent")
        details = parent.get("subscription_details") if isinstance(parent, dict) else None
        subscription_id = (
            _optional_object_id(details.get("subscription")) if isinstance(details, dict) else None
        )
    transitions = value.get("status_transitions")
    paid_at = transitions.get("paid_at") if isinstance(transitions, dict) else None
    return InvoiceSnapshot(
        provider_invoice_id=_required_text(value.get("id"), 255),
        provider_customer_id=customer_id,
        provider_subscription_id=subscription_id,
        invoice_number=_optional_text(value.get("number"), 120),
        status=_required_text(value.get("status"), 32).lower(),
        currency=_required_text(value.get("currency"), 3).upper(),
        amount_due_minor=_nonnegative_int(value.get("amount_due")),
        amount_paid_minor=_nonnegative_int(value.get("amount_paid")),
        provider_created_at=_optional_timestamp(value.get("created")),
        due_at=_optional_timestamp(value.get("due_date")),
        paid_at=_optional_timestamp(paid_at),
    )


def _metadata(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _object_id(value: object) -> str:
    result = _optional_object_id(value)
    if result is None:
        _invalid_webhook()
    return result


def _optional_object_id(value: object) -> str | None:
    if isinstance(value, str):
        return _optional_text(value, 255)
    if isinstance(value, dict):
        return _optional_text(value.get("id"), 255)
    return None


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name:
            return value
    _invalid_webhook()


def _parse_signature(value: str) -> tuple[int, tuple[str, ...]]:
    if len(value) > 4_096:
        _invalid_webhook()
    timestamp: int | None = None
    signatures: list[str] = []
    for part in value.split(","):
        key, separator, raw = part.strip().partition("=")
        if separator != "=" or not raw:
            continue
        if key == "t":
            try:
                candidate = int(raw)
            except ValueError:
                _invalid_webhook()
            if timestamp is not None or candidate <= 0:
                _invalid_webhook()
            timestamp = candidate
        elif key == "v1" and len(raw) == 64:
            signatures.append(raw.lower())
    if timestamp is None or not signatures:
        _invalid_webhook()
    return timestamp, tuple(signatures)


def _required_text(value: object, maximum: int) -> str:
    result = _optional_text(value, maximum)
    if result is None:
        _invalid_webhook()
    return result


def _optional_text(value: object, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        _invalid_webhook()
    normalized = value.strip()
    if not normalized or len(normalized) > maximum or any(ord(char) < 32 for char in normalized):
        _invalid_webhook()
    return normalized


def _optional_sha256(value: object) -> str | None:
    result = _optional_text(value, 64)
    if result is not None and (
        len(result) != 64 or any(character not in "0123456789abcdef" for character in result)
    ):
        _invalid_webhook()
    return result


def _required_timestamp(value: object) -> datetime:
    result = _optional_timestamp(value)
    if result is None:
        _invalid_webhook()
    return result


def _optional_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _invalid_webhook()
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError):
        _invalid_webhook()


def _optional_positive_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def _nonnegative_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _invalid_webhook()
    return value


def _reject_json_constant(_: str) -> NoReturn:
    raise ValueError("Non-finite JSON number")


def _invalid_webhook() -> NoReturn:
    raise WebhookVerificationError("Webhook verification failed")
