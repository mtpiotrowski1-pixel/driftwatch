"""Strict request/response contracts for billing APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_IDEMPOTENCY_KEY = r"^[A-Za-z0-9._:-]+$"


class CheckoutCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    billing_price_id: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=_IDEMPOTENCY_KEY)
    accepted_terms_version: str = Field(min_length=1, max_length=80)
    accepted_privacy_version: str = Field(min_length=1, max_length=80)
    accepted_terms_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted_privacy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PortalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=100, pattern=_IDEMPOTENCY_KEY)


class HostedSessionOut(BaseModel):
    url: str
    expires_at: datetime | None = None


class BillingPriceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: int = Field(gt=0)
    provider: Literal["stripe"]
    provider_price_id: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9_]+$")
    unit_amount_minor: int = Field(ge=0, le=1_000_000_000)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    recurring_interval: Literal["day", "week", "month", "year"] = "month"
    interval_count: int = Field(default=1, ge=1, le=36)


class BillingPriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    provider: str
    provider_price_id: str
    version: int
    unit_amount_minor: int
    currency: str
    recurring_interval: str
    interval_count: int
    is_active: bool
    created_at: datetime
    retired_at: datetime | None = None


class BillingCatalogPriceOut(BaseModel):
    billing_price_id: int
    price_version: int
    plan_id: int
    plan_key: str
    plan_name: str
    max_sites: int | None = None
    max_members: int | None = None
    monthly_ai_check_limit: int | None = None
    unit_amount_minor: int
    currency: str
    recurring_interval: str
    interval_count: int


class BillingCatalogOut(BaseModel):
    self_serve_ready: bool
    terms_version: str | None = None
    privacy_version: str | None = None
    terms_url: str | None = None
    privacy_url: str | None = None
    terms_sha256: str | None = None
    privacy_sha256: str | None = None
    prices: list[BillingCatalogPriceOut]


class SubscriptionStatusOut(BaseModel):
    status: str
    plan_id: int | None = None
    plan_key: str | None = None
    plan_name: str | None = None
    current_period_end: datetime | None = None
    trial_end: datetime | None = None
    cancel_at_period_end: bool
    entitlement_active: bool
    entitlement_valid_until: datetime | None = None
    access_suspended_at: datetime | None = None


class BillingStatusOut(BaseModel):
    provider: str
    provider_configured: bool
    self_serve_ready: bool
    customer_exists: bool
    subscription: SubscriptionStatusOut | None = None


class WebhookAcceptedOut(BaseModel):
    received: bool = True
    duplicate: bool


class ReconciliationOut(BaseModel):
    organization_id: int
    subscriptions_seen: int
    subscriptions_updated: int
