"""Construct the configured billing adapter without enabling self-service."""

from __future__ import annotations

from driftwatch.billing.provider import BillingProvider, DisabledBillingProvider
from driftwatch.billing.stripe import StripeBillingProvider
from driftwatch.config import Settings


def build_billing_provider(settings: Settings) -> BillingProvider:
    if not settings.billing_provider_configured:
        return DisabledBillingProvider()
    return StripeBillingProvider(
        api_key=settings.stripe_secret_key.get_secret_value(),
        webhook_secret=settings.stripe_webhook_secret.get_secret_value(),
        api_version=settings.stripe_api_version,
        base_url=settings.stripe_api_base_url,
        timeout_seconds=settings.stripe_timeout_seconds,
        webhook_tolerance_seconds=settings.billing_webhook_tolerance_seconds,
    )
