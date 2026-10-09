"""SQLAlchemy ORM models for Driftwatch.

The schema models a small, shared monitoring workspace: ``Site`` rows are
checked on their own schedule, each check stores a ``Snapshot`` and, when the
content meaningfully changed, a ``ChangeEvent`` carrying the diff and the AI
verdict. Sites can be grouped into ``Project`` workspaces that supply default AI
rules and notification settings, and ``Recipient`` rows are notified either per
site or per project.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftwatch.db import Base
from driftwatch.enums import (
    AccountEmailKind,
    AccountEmailStatus,
    AnalysisMode,
    AnalysisStatus,
    CheckJobKind,
    CheckJobSource,
    CheckJobStatus,
    NotificationDeliveryStatus,
    NotificationMode,
    NotificationStatus,
    RetryStatus,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


site_recipients = Table(
    "site_recipients",
    Base.metadata,
    Column("site_id", ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True),
    Column("recipient_id", ForeignKey("recipients.id", ondelete="CASCADE"), primary_key=True),
)

project_recipients = Table(
    "project_recipients",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("recipient_id", ForeignKey("recipients.id", ondelete="CASCADE"), primary_key=True),
)

# Edit grants for non-admin members. A project grant covers the project and every
# site inside it; a site grant covers a single site.
project_editors = Table(
    "project_editors",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)

site_editors = Table(
    "site_editors",
    Base.metadata,
    Column("site_id", ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class Organization(Base):
    """A tenant: an isolated workspace of projects, sites, recipients, and members.

    One instance can host several organizations (a company with multiple
    subsidiaries, or an operator serving several clients). Data is scoped per
    organization; the instance superadmin sees and manages all of them. Hard
    isolation between unrelated clients is still achievable per-deployment
    (a separate database per client)."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Billing plan label and its enforced limits. These are set only by the
    # instance operator (superadmin), never by an org's own admin, so a customer
    # cannot raise their own caps. NULL means unlimited.
    plan: Mapped[str] = mapped_column(String(40), default="free")
    max_sites: Mapped[int | None] = mapped_column(Integer)
    max_members: Mapped[int | None] = mapped_column(Integer)
    monthly_ai_check_limit: Mapped[int | None] = mapped_column(Integer)
    # Transactional quota counters. They are reconciled against the underlying
    # rows on every reservation, so a legacy/manual insert cannot make them
    # under-count. Reservations and resource creation share one transaction.
    site_slots_used: Mapped[int] = mapped_column(Integer, default=0)
    member_slots_used: Mapped[int] = mapped_column(Integer, default=0)
    ai_usage_month: Mapped[str | None] = mapped_column(String(7))
    ai_checks_reserved: Mapped[int] = mapped_column(Integer, default=0)
    # Persistent round-robin cursor used by the cross-replica check queue.
    check_queue_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set only when billing suspends the tenant, so a later paid event can safely
    # reactivate it without overriding an operator's manual deactivation.
    billing_suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Independent of billing state: paid events may clear billing suspension but
    # must never undo a deliberate operator suspension.
    manually_suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The catalog plan this org is on, if assigned from one. Assigning a plan
    # copies its caps onto the columns above; this link only records which plan
    # they came from. A deleted plan detaches (SET NULL) and leaves the caps.
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Plan(Base):
    """A subscription tier the operator sells: the caps it enforces and its monthly
    price. Defined once in the catalog and assigned to organizations, instead of
    typing caps and prices into each org by hand. Operator-controlled — a customer
    can neither see nor change the catalog."""

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    # NULL cap means unlimited, matching Organization's columns.
    max_sites: Mapped[int | None] = mapped_column(Integer)
    max_members: Mapped[int | None] = mapped_column(Integer)
    monthly_ai_check_limit: Mapped[int | None] = mapped_column(Integer)
    # Price override in minor units (e.g. cents) to keep money off floats. NULL
    # means the price follows the pricing algorithm — the default catalogue —
    # so retuning the knobs re-prices every plan that isn't pinned. A value pins
    # a fixed price the operator chose.
    price_override_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Whether a public sign-up may put itself on this plan (and see it on the
    # public pricing page). Off by default: a customer cannot self-grant a tier's
    # caps unless the operator opts it in. Higher tiers stay operator-assigned.
    is_self_serve: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class BillingCustomer(Base):
    """Provider customer identity mapped to exactly one tenant."""

    __tablename__ = "billing_customers"
    __table_args__ = (
        UniqueConstraint("organization_id", "provider"),
        UniqueConstraint("provider", "provider_customer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    provider_customer_id: Mapped[str] = mapped_column(String(255))
    terms_version: Mapped[str | None] = mapped_column(String(80))
    privacy_version: Mapped[str | None] = mapped_column(String(80))
    terms_sha256: Mapped[str | None] = mapped_column(String(64))
    privacy_sha256: Mapped[str | None] = mapped_column(String(64))
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consented_by_user_id: Mapped[int | None] = mapped_column(Integer)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class BillingPrice(Base):
    """A versioned local record of an externally created recurring price."""

    __tablename__ = "billing_prices"
    __table_args__ = (
        UniqueConstraint("plan_id", "provider", "version"),
        UniqueConstraint("provider", "provider_price_id"),
        CheckConstraint("version >= 1", name="ck_billing_prices_version_positive"),
        CheckConstraint("unit_amount_minor >= 0", name="ck_billing_prices_amount_nonnegative"),
        CheckConstraint("interval_count >= 1", name="ck_billing_prices_interval_positive"),
        Index("ix_billing_prices_catalog", "provider", "plan_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_price_id: Mapped[str] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer)
    unit_amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    recurring_interval: Mapped[str] = mapped_column(String(16), default="month")
    interval_count: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CheckoutAttempt(Base):
    """Durable checkout idempotency record; contains no payment method data."""

    __tablename__ = "billing_checkout_attempts"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key"),
        UniqueConstraint("organization_id", "active_marker"),
        Index("ix_billing_checkout_attempts_status", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    billing_price_id: Mapped[int] = mapped_column(
        ForeignKey("billing_prices.id", ondelete="RESTRICT"), index=True
    )
    requested_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(100))
    terms_version: Mapped[str] = mapped_column(String(80))
    privacy_version: Mapped[str] = mapped_column(String(80))
    terms_sha256: Mapped[str | None] = mapped_column(String(64))
    privacy_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    active_marker: Mapped[bool | None] = mapped_column(Boolean, default=True)
    provider_session_id: Mapped[str | None] = mapped_column(String(255))
    hosted_url: Mapped[str | None] = mapped_column(String(2048))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Subscription(Base):
    """Provider subscription projection; webhooks and reconciliation are authoritative."""

    __tablename__ = "billing_subscriptions"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subscription_id"),
        Index("ix_billing_subscriptions_org_status", "organization_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    billing_customer_id: Mapped[int] = mapped_column(
        ForeignKey("billing_customers.id", ondelete="RESTRICT"), index=True
    )
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"))
    provider: Mapped[str] = mapped_column(String(32))
    provider_subscription_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), index=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    past_due_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    access_suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class SubscriptionItem(Base):
    __tablename__ = "billing_subscription_items"
    __table_args__ = (
        UniqueConstraint("subscription_id", "provider_item_id"),
        CheckConstraint("quantity >= 1", name="ck_billing_subscription_items_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("billing_subscriptions.id", ondelete="CASCADE"), index=True
    )
    billing_price_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_prices.id", ondelete="SET NULL"), index=True
    )
    provider_item_id: Mapped[str] = mapped_column(String(255))
    provider_price_id: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class InvoiceReference(Base):
    """Minimal invoice projection: amounts and identifiers, never payment method data."""

    __tablename__ = "billing_invoice_references"
    __table_args__ = (
        UniqueConstraint("provider", "provider_invoice_id"),
        CheckConstraint("amount_due_minor >= 0", name="ck_billing_invoices_due_nonnegative"),
        CheckConstraint("amount_paid_minor >= 0", name="ck_billing_invoices_paid_nonnegative"),
        Index("ix_billing_invoices_org_created", "organization_id", "provider_created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    billing_customer_id: Mapped[int] = mapped_column(
        ForeignKey("billing_customers.id", ondelete="RESTRICT"), index=True
    )
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_subscriptions.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    provider_invoice_id: Mapped[str] = mapped_column(String(255))
    invoice_number: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3))
    amount_due_minor: Mapped[int] = mapped_column(Integer, default=0)
    amount_paid_minor: Mapped[int] = mapped_column(Integer, default=0)
    provider_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class EntitlementGrant(Base):
    __tablename__ = "billing_entitlement_grants"
    __table_args__ = (
        UniqueConstraint("subscription_id", "entitlement_key"),
        Index("ix_billing_entitlements_org_active", "organization_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("billing_subscriptions.id", ondelete="RESTRICT"), index=True
    )
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"))
    entitlement_key: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class BillingEvent(Base):
    """Append-only, sanitized provider event ledger used for idempotent ingestion."""

    __tablename__ = "billing_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id"),
        Index("ix_billing_events_received", "provider", "received_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_event_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(255))
    organization_id: Mapped[int | None] = mapped_column(Integer, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    livemode: Mapped[bool] = mapped_column(Boolean, default=False)
    api_version: Mapped[str | None] = mapped_column(String(40))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    resource_data: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


@event.listens_for(BillingEvent, "before_update")
@event.listens_for(BillingEvent, "before_delete")
def _protect_billing_event(*_: object) -> None:
    raise RuntimeError("Billing events are append-only")


class BillingEventProcessing(Base):
    """Mutable processing state kept outside the immutable provider event."""

    __tablename__ = "billing_event_processing"

    billing_event_id: Mapped[int] = mapped_column(
        ForeignKey("billing_events.id", ondelete="RESTRICT"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(32), default="received", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    # An org member/admin belongs to one organization; a superadmin (instance
    # operator) may be org-less and sees every organization.
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Bumped on password change/reset to invalidate every issued session token.
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    # Random identity bound into every session and purpose-scoped token. Unlike
    # the numeric primary key/version pair, it cannot be resurrected by an ID
    # reuse or database restore.
    session_generation: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid4()))
    # Two-factor auth: the base32 TOTP secret is stored encrypted; recovery codes
    # are kept as single-use hashes. ``totp_enabled`` gates the second login step.
    totp_secret: Mapped[str | None] = mapped_column(String(255))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Login challenges are single-use even when a cookie is copied. The last
    # accepted counter fences simultaneous logins using the same TOTP step.
    pending_totp_nonce: Mapped[str | None] = mapped_column(String(36))
    totp_last_login_counter: Mapped[int | None] = mapped_column(Integer)
    recovery_code_hashes: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountEmailJob(Base):
    """Durable request for a password reset or account invitation.

    The recipient address and generated token deliberately never enter this
    table. Delivery resolves the current user and tenant settings only after a
    worker has obtained a lease, then generates a short-lived token in memory.
    """

    __tablename__ = "account_email_jobs"
    __table_args__ = (
        UniqueConstraint("kind", "active_key", name="uq_account_email_jobs_active"),
        Index(
            "ix_account_email_jobs_claim",
            "status",
            "next_attempt_at",
            "lease_expires_at",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_account_email_jobs_attempt_count"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[AccountEmailKind] = mapped_column(String(32))
    status: Mapped[AccountEmailStatus] = mapped_column(
        String(16), default=AccountEmailStatus.PENDING
    )
    # HMAC-derived while active and cleared on a terminal state. It coalesces
    # retries without persisting a reversible recipient identifier.
    active_key: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class AuditEvent(Base):
    """Immutable application audit record for privileged control-plane actions.

    Actor and organization identifiers intentionally are not foreign keys. An
    account or tenant deletion must not erase, cascade, or anonymize the record
    that explains who performed it. The accompanying labels are point-in-time
    snapshots, so the trail remains useful after later renames.
    """

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_organization_id_id", "organization_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    actor_user_id: Mapped[int] = mapped_column(Integer, index=True)
    actor_email: Mapped[str] = mapped_column(String(320))
    actor_is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    organization_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_type: Mapped[str] = mapped_column(String(60))
    target_id: Mapped[str | None] = mapped_column(String(120))
    target_label: Mapped[str | None] = mapped_column(String(320))
    source_ip: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


@event.listens_for(AuditEvent, "before_update")
@event.listens_for(AuditEvent, "before_delete")
def _protect_audit_event(*_: object) -> None:
    """Keep the audit ledger append-only through every ORM write path."""
    raise RuntimeError("Audit events are append-only")


class SupportAccessGrant(Base):
    """Server-authoritative break-glass access to one customer organization.

    The signed cookie identifies a grant, but this row remains the authority for
    every write decision. Keeping revocation server-side prevents a copied cookie
    from being replayed after an operator ends the support session.
    """

    __tablename__ = "support_access_grants"
    __table_args__ = (UniqueConstraint("operator_user_id", "organization_id", "active_marker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    operator_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    grant_event_id: Mapped[int] = mapped_column(
        ForeignKey("audit_events.id", ondelete="RESTRICT"), unique=True
    )
    active_marker: Mapped[bool | None] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    prompt: Mapped[str | None] = mapped_column(Text)
    notification_mode: Mapped[NotificationMode | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    sites: Mapped[list[Site]] = relationship(back_populates="project")
    recipients: Mapped[list[Recipient]] = relationship(secondary=project_recipients)


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    url: Mapped[str] = mapped_column(String(2048))
    name: Mapped[str | None] = mapped_column(String(200))
    css_selector: Mapped[str | None] = mapped_column(String(500))
    prompt: Mapped[str | None] = mapped_column(Text)
    interaction_steps: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    check_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notification_mode: Mapped[NotificationMode | None] = mapped_column(String(32))
    analysis_mode: Mapped[AnalysisMode] = mapped_column(String(16), default=AnalysisMode.AI)
    ignore_selectors: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Last operational alert (e.g. selector vanished, page blocked) and when it
    # was sent — used to throttle repeat alerts for the same condition. The
    # detail keeps the underlying error message so the UI can explain the badge
    # (DNS failure vs timeout) without digging through logs.
    last_alert_code: Mapped[str | None] = mapped_column(String(40))
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_alert_detail: Mapped[str | None] = mapped_column(Text)
    # Captures failed in a row since the last success; reaching the
    # org-overridable threshold escalates to a "site appears down" alert.
    consecutive_failure_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    project: Mapped[Project | None] = relationship(back_populates="sites")
    recipients: Mapped[list[Recipient]] = relationship(secondary=site_recipients)
    snapshots: Mapped[list[Snapshot]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )
    changes: Mapped[list[ChangeEvent]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )
    interaction_secrets: Mapped[list[InteractionSecret]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )


class CheckQueueState(Base):
    """Singleton row used only to serialize queue-capacity reservations."""

    __tablename__ = "check_queue_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SiteCheckJob(Base):
    """Durable capture/check work shared by schedulers and manual requests."""

    __tablename__ = "site_check_jobs"
    __table_args__ = (
        CheckConstraint(
            "(source <> 'redrive' AND original_job_id IS NULL "
            "AND redrive_request_sha256 IS NULL) OR "
            "(source = 'redrive' AND redrive_request_sha256 IS NOT NULL "
            "AND length(redrive_request_sha256) = 64)",
            name="ck_site_check_jobs_redrive_metadata",
        ),
        CheckConstraint(
            "original_job_id IS NULL OR original_job_id <> id",
            name="ck_site_check_jobs_original_not_self",
        ),
        Index(
            "ix_site_check_jobs_claim",
            "status",
            "available_at",
            "lease_expires_at",
            "enqueued_at",
        ),
        Index("ix_site_check_jobs_org_status", "organization_id", "status"),
        Index(
            "ux_site_check_jobs_original_job_id",
            "original_job_id",
            unique=True,
            sqlite_where=text("original_job_id IS NOT NULL"),
            postgresql_where=text("original_job_id IS NOT NULL"),
        ),
        Index(
            "ix_site_check_jobs_active_site",
            "site_id",
            unique=True,
            sqlite_where=text("status IN ('pending', 'running')"),
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    original_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("site_check_jobs.id", ondelete="SET NULL")
    )
    redrive_request_sha256: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    kind: Mapped[CheckJobKind] = mapped_column(String(16))
    source: Mapped[CheckJobSource] = mapped_column(String(16))
    analyze: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[CheckJobStatus] = mapped_column(String(16), default=CheckJobStatus.PENDING)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=_utcnow)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, object] | None] = mapped_column(JSON)


class InteractionSecret(Base):
    """Encrypted value referenced by a site's ``fill`` interaction step.

    The site's JSON script contains only the opaque UUID. Keeping ciphertext in
    a separate, tenant-scoped row prevents ordinary site reads, exports, and
    JSON backups from accidentally treating a secret as step configuration.
    """

    __tablename__ = "interaction_secrets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    site: Mapped[Site] = relationship(back_populates="interaction_secrets")


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    content_html: Mapped[str] = mapped_column(Text)
    content_text: Mapped[str] = mapped_column(Text, default="")
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    site: Mapped[Site] = relationship(back_populates="snapshots")


class ChangeEvent(Base):
    __tablename__ = "changes"
    # The hot read is "this site's changes, newest first" (detail page, export,
    # aggregates); a composite index serves it without a filesort. The second
    # index supports the per-tick retry sweep's predicate+order.
    __table_args__ = (
        Index("ix_changes_site_created", "site_id", "created_at"),
        Index("ix_changes_retry", "retry_status", "next_retry_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    old_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("snapshots.id"))
    new_snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"))

    diff_text: Mapped[str] = mapped_column(Text, default="")
    diff_html: Mapped[str] = mapped_column(Text, default="")

    # AI verdict. ``significant`` is None until analysis succeeds; ``ai_error``
    # marks a verdict that failed and may be retried — never treated as "not
    # significant", so no email is sent on an uncertain analysis.
    significant: Mapped[bool | None] = mapped_column(Boolean)
    headline: Mapped[str | None] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)
    ai_error: Mapped[str | None] = mapped_column(Text)
    ai_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    analysis_status: Mapped[AnalysisStatus] = mapped_column(
        String(24), default=AnalysisStatus.NOT_REQUESTED
    )
    analysis_lease_token: Mapped[str | None] = mapped_column(String(36))
    analysis_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Human verdict on significance, stored beside — never over — the AI's own
    # ``significant``, so feedback can measure the model without rewriting
    # history. NULL means nobody has reviewed the verdict yet.
    user_verdict: Mapped[bool | None] = mapped_column(Boolean)
    user_verdict_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_verdict_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # Delivery retry state. ``retry_status`` is None while a change can still be
    # retried automatically and flips to ``requires_action`` once attempts are
    # exhausted, surfacing it in the action-required queue.
    notification_error: Mapped[str | None] = mapped_column(Text)
    notification_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    retry_status: Mapped[RetryStatus | None] = mapped_column(String(20))

    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    site: Mapped[Site] = relationship(back_populates="changes")


class LinkedAsset(Base):
    """Fingerprint of a document linked from a monitored page.

    A PDF replaced under the same URL never shows up in the page diff — the
    link text is unchanged. When an organization opts in, the check pipeline
    HEAD-probes document links and stores the validator headers here; a changed
    fingerprint synthesizes a content-block change that rides the normal
    diff -> ChangeEvent -> analyzer path."""

    __tablename__ = "linked_assets"
    __table_args__ = (UniqueConstraint("site_id", "url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    etag: Mapped[str | None] = mapped_column(String(255))
    last_modified: Mapped[str | None] = mapped_column(String(255))
    content_length: Mapped[int | None] = mapped_column(Integer)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AnalysisRun(Base):
    """One successful AI analysis of a change.

    Re-analysis overwrites the verdict fields on :class:`ChangeEvent`, so this
    append-only log preserves what earlier analyses said — the change view can
    show how a verdict evolved instead of silently losing history. Rows follow
    their change (ON DELETE CASCADE), so retention pruning needs no extra step.
    """

    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    change_id: Mapped[int] = mapped_column(ForeignKey("changes.id", ondelete="CASCADE"), index=True)
    significant: Mapped[bool] = mapped_column(Boolean)
    headline: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    # Nullable only for history created before provenance was recorded. Never
    # reconstruct old runs from today's mutable site/settings configuration.
    model: Mapped[str | None] = mapped_column(String(80))
    rules_source: Mapped[str | None] = mapped_column(String(16))
    rules_version: Mapped[str | None] = mapped_column(String(64))
    system_prompt: Mapped[str | None] = mapped_column(Text)
    input_sha256: Mapped[str | None] = mapped_column(String(64))
    input_truncated: Mapped[bool | None] = mapped_column(Boolean)
    usage_id: Mapped[int | None] = mapped_column(ForeignKey("ai_usage.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Recipient(Base):
    __tablename__ = "recipients"
    # Email is unique within an organization, not globally — two orgs may notify
    # the same address, and a global unique would also leak existence across orgs.
    __table_args__ = (UniqueConstraint("organization_id", "email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    substitutions: Mapped[list[RecipientSubstitution]] = relationship(
        back_populates="recipient", cascade="all, delete-orphan"
    )


class RecipientSubstitution(Base):
    """Redirects a recipient's mail to a stand-in over an inclusive date range.

    A substitution covers all of the recipient's notifications by default. It can
    instead be confined to one project or one site (never both): then it only
    redirects alerts for that scope, leaving the rest of the recipient's mail
    untouched. A site-scoped cover is more specific than a project-scoped one,
    which is more specific than an unscoped one.
    """

    __tablename__ = "recipient_substitutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("recipients.id", ondelete="CASCADE"), index=True
    )
    # Optional, mutually-exclusive scope; both NULL means "all notifications".
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, default=None
    )
    site_id: Mapped[int | None] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), index=True, default=None
    )
    substitute_email: Mapped[str] = mapped_column(String(320))
    substitute_name: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[str] = mapped_column(String(10))  # ISO YYYY-MM-DD, inclusive
    end_date: Mapped[str] = mapped_column(String(10))  # ISO YYYY-MM-DD, inclusive
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    recipient: Mapped[Recipient] = relationship(back_populates="substitutions")


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    change_id: Mapped[int] = mapped_column(ForeignKey("changes.id", ondelete="CASCADE"), index=True)
    recipient_email: Mapped[str] = mapped_column(String(320))
    channel: Mapped[str] = mapped_column(String(32))
    status: Mapped[NotificationStatus] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(String(255))
    # The audit log is always read newest-first.
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class NotificationOutbox(Base):
    """One immutable notification intent for a detected change.

    The unique change and idempotency keys make enqueue safe to repeat. Delivery
    targets are captured in the same transaction as this row, before any
    provider is called.
    """

    __tablename__ = "notification_outboxes"

    id: Mapped[int] = mapped_column(primary_key=True)
    change_id: Mapped[int] = mapped_column(
        ForeignKey("changes.id", ondelete="CASCADE"), unique=True, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    deliveries: Mapped[list[NotificationDelivery]] = relationship(
        back_populates="outbox", cascade="all, delete-orphan"
    )


class NotificationDelivery(Base):
    """Retry and lease state for one email address or webhook endpoint."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("outbox_id", "destination_key"),
        Index(
            "ix_notification_deliveries_claim",
            "status",
            "next_attempt_at",
            "lease_expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    outbox_id: Mapped[int] = mapped_column(
        ForeignKey("notification_outboxes.id", ondelete="CASCADE"), index=True
    )
    destination_key: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    destination_label: Mapped[str] = mapped_column(String(320))
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    target_ciphertext: Mapped[str | None] = mapped_column(Text)
    status: Mapped[NotificationDeliveryStatus] = mapped_column(
        String(16), default=NotificationDeliveryStatus.PENDING
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    outbox: Mapped[NotificationOutbox] = relationship(back_populates="deliveries")


class AIUsage(Base):
    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Immutable billing/usage ownership. Unlike site_id this survives deletion
    # of the monitored site, so removing a site cannot reset a monthly limit or
    # erase tenant cost attribution.
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    site_id: Mapped[int | None] = mapped_column(
        ForeignKey("sites.id", ondelete="SET NULL"), index=True
    )
    change_id: Mapped[int | None] = mapped_column(ForeignKey("changes.id", ondelete="SET NULL"))
    model: Mapped[str] = mapped_column(String(80))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    pricing_source: Mapped[str] = mapped_column(String(24), default="legacy")
    purpose: Mapped[str] = mapped_column(String(16), default="change")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class InstanceBootstrap(Base):
    """One-time ownership claim, independent of user deletion and editable settings."""

    __tablename__ = "instance_bootstrap"
    __table_args__ = (CheckConstraint("id = 1", name="ck_instance_bootstrap_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Setting(Base):
    """Instance-wide default settings (one row per key). Per-organization
    overrides live in :class:`OrgSetting`; a missing override inherits this row."""

    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("key"),)

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class OrgSetting(Base):
    """A per-organization override of a setting. Its absence means the
    organization inherits the instance default from :class:`Setting`."""

    __tablename__ = "org_settings"
    __table_args__ = (UniqueConstraint("organization_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(Text)
