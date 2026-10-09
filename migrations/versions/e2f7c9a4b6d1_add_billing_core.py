"""add provider-agnostic billing ledger and projections

Revision ID: e2f7c9a4b6d1
Revises: d0f6b8c2a4e1
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2f7c9a4b6d1"
down_revision: str | None = "d0f6b8c2a4e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPDATE_TRIGGER = "trg_billing_events_no_update"
_DELETE_TRIGGER = "trg_billing_events_no_delete"
_POSTGRES_FUNCTION = "driftwatch_reject_billing_event_mutation"


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("billing_suspended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "billing_customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_customer_id", sa.String(length=255), nullable=False),
        sa.Column("terms_version", sa.String(length=80), nullable=True),
        sa.Column("privacy_version", sa.String(length=80), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consented_by_user_id", sa.Integer(), nullable=True),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "provider"),
        sa.UniqueConstraint("provider", "provider_customer_id"),
    )
    op.create_index(
        "ix_billing_customers_organization_id",
        "billing_customers",
        ["organization_id"],
    )
    op.create_table(
        "billing_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_price_id", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("unit_amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("recurring_interval", sa.String(length=16), nullable=False),
        sa.Column("interval_count", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("interval_count >= 1", name="ck_billing_prices_interval_positive"),
        sa.CheckConstraint("unit_amount_minor >= 0", name="ck_billing_prices_amount_nonnegative"),
        sa.CheckConstraint("version >= 1", name="ck_billing_prices_version_positive"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "provider", "version"),
        sa.UniqueConstraint("provider", "provider_price_id"),
    )
    op.create_index(
        "ix_billing_prices_catalog",
        "billing_prices",
        ["provider", "plan_id", "is_active"],
    )
    op.create_index("ix_billing_prices_plan_id", "billing_prices", ["plan_id"])
    op.create_table(
        "billing_checkout_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("billing_price_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("terms_version", sa.String(length=80), nullable=False),
        sa.Column("privacy_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("active_marker", sa.Boolean(), nullable=True),
        sa.Column("provider_session_id", sa.String(length=255), nullable=True),
        sa.Column("hosted_url", sa.String(length=2048), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["billing_price_id"], ["billing_prices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "idempotency_key"),
        sa.UniqueConstraint("organization_id", "active_marker"),
    )
    op.create_index(
        "ix_billing_checkout_attempts_billing_price_id",
        "billing_checkout_attempts",
        ["billing_price_id"],
    )
    op.create_index(
        "ix_billing_checkout_attempts_organization_id",
        "billing_checkout_attempts",
        ["organization_id"],
    )
    op.create_index(
        "ix_billing_checkout_attempts_requested_by_user_id",
        "billing_checkout_attempts",
        ["requested_by_user_id"],
    )
    op.create_index(
        "ix_billing_checkout_attempts_status",
        "billing_checkout_attempts",
        ["status", "updated_at"],
    )
    op.create_table(
        "billing_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("billing_customer_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_subscription_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("past_due_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["billing_customer_id"], ["billing_customers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_subscription_id"),
    )
    op.create_index(
        "ix_billing_subscriptions_billing_customer_id",
        "billing_subscriptions",
        ["billing_customer_id"],
    )
    op.create_index(
        "ix_billing_subscriptions_organization_id",
        "billing_subscriptions",
        ["organization_id"],
    )
    op.create_index(
        "ix_billing_subscriptions_org_status",
        "billing_subscriptions",
        ["organization_id", "status"],
    )
    op.create_index("ix_billing_subscriptions_status", "billing_subscriptions", ["status"])
    op.create_table(
        "billing_subscription_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("billing_price_id", sa.Integer(), nullable=True),
        sa.Column("provider_item_id", sa.String(length=255), nullable=False),
        sa.Column("provider_price_id", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="ck_billing_subscription_items_quantity_positive"),
        sa.ForeignKeyConstraint(["billing_price_id"], ["billing_prices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["billing_subscriptions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id", "provider_item_id"),
    )
    op.create_index(
        "ix_billing_subscription_items_billing_price_id",
        "billing_subscription_items",
        ["billing_price_id"],
    )
    op.create_index(
        "ix_billing_subscription_items_subscription_id",
        "billing_subscription_items",
        ["subscription_id"],
    )
    op.create_table(
        "billing_invoice_references",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("billing_customer_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_invoice_id", sa.String(length=255), nullable=False),
        sa.Column("invoice_number", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount_due_minor", sa.Integer(), nullable=False),
        sa.Column("amount_paid_minor", sa.Integer(), nullable=False),
        sa.Column("provider_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_due_minor >= 0", name="ck_billing_invoices_due_nonnegative"),
        sa.CheckConstraint("amount_paid_minor >= 0", name="ck_billing_invoices_paid_nonnegative"),
        sa.ForeignKeyConstraint(
            ["billing_customer_id"], ["billing_customers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["billing_subscriptions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_invoice_id"),
    )
    op.create_index(
        "ix_billing_invoices_billing_customer_id",
        "billing_invoice_references",
        ["billing_customer_id"],
    )
    op.create_index(
        "ix_billing_invoices_org_created",
        "billing_invoice_references",
        ["organization_id", "provider_created_at"],
    )
    op.create_index(
        "ix_billing_invoices_organization_id",
        "billing_invoice_references",
        ["organization_id"],
    )
    op.create_index(
        "ix_billing_invoices_subscription_id",
        "billing_invoice_references",
        ["subscription_id"],
    )
    op.create_table(
        "billing_entitlement_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("entitlement_key", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["billing_subscriptions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id", "entitlement_key"),
    )
    op.create_index(
        "ix_billing_entitlements_org_active",
        "billing_entitlement_grants",
        ["organization_id", "is_active"],
    )
    op.create_index(
        "ix_billing_entitlements_organization_id",
        "billing_entitlement_grants",
        ["organization_id"],
    )
    op.create_index(
        "ix_billing_entitlements_subscription_id",
        "billing_entitlement_grants",
        ["subscription_id"],
    )
    op.create_table(
        "billing_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("livemode", sa.Boolean(), nullable=False),
        sa.Column("api_version", sa.String(length=40), nullable=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("resource_data", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_event_id"),
    )
    op.create_index("ix_billing_events_event_type", "billing_events", ["event_type"])
    op.create_index("ix_billing_events_occurred_at", "billing_events", ["occurred_at"])
    op.create_index("ix_billing_events_organization_id", "billing_events", ["organization_id"])
    op.create_index(
        "ix_billing_events_received",
        "billing_events",
        ["provider", "received_at"],
    )
    op.create_table(
        "billing_event_processing",
        sa.Column("billing_event_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["billing_event_id"], ["billing_events.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("billing_event_id"),
    )
    op.create_index(
        "ix_billing_event_processing_status",
        "billing_event_processing",
        ["status"],
    )
    _create_immutability_triggers()


def downgrade() -> None:
    _drop_immutability_triggers()
    op.drop_index("ix_billing_event_processing_status", table_name="billing_event_processing")
    op.drop_table("billing_event_processing")
    op.drop_index("ix_billing_events_received", table_name="billing_events")
    op.drop_index("ix_billing_events_organization_id", table_name="billing_events")
    op.drop_index("ix_billing_events_occurred_at", table_name="billing_events")
    op.drop_index("ix_billing_events_event_type", table_name="billing_events")
    op.drop_table("billing_events")
    op.drop_index(
        "ix_billing_entitlements_subscription_id", table_name="billing_entitlement_grants"
    )
    op.drop_index(
        "ix_billing_entitlements_organization_id", table_name="billing_entitlement_grants"
    )
    op.drop_index("ix_billing_entitlements_org_active", table_name="billing_entitlement_grants")
    op.drop_table("billing_entitlement_grants")
    op.drop_index("ix_billing_invoices_subscription_id", table_name="billing_invoice_references")
    op.drop_index("ix_billing_invoices_organization_id", table_name="billing_invoice_references")
    op.drop_index("ix_billing_invoices_org_created", table_name="billing_invoice_references")
    op.drop_index(
        "ix_billing_invoices_billing_customer_id", table_name="billing_invoice_references"
    )
    op.drop_table("billing_invoice_references")
    op.drop_index(
        "ix_billing_subscription_items_subscription_id",
        table_name="billing_subscription_items",
    )
    op.drop_index(
        "ix_billing_subscription_items_billing_price_id",
        table_name="billing_subscription_items",
    )
    op.drop_table("billing_subscription_items")
    op.drop_index("ix_billing_subscriptions_status", table_name="billing_subscriptions")
    op.drop_index("ix_billing_subscriptions_org_status", table_name="billing_subscriptions")
    op.drop_index("ix_billing_subscriptions_organization_id", table_name="billing_subscriptions")
    op.drop_index(
        "ix_billing_subscriptions_billing_customer_id", table_name="billing_subscriptions"
    )
    op.drop_table("billing_subscriptions")
    op.drop_index("ix_billing_checkout_attempts_status", table_name="billing_checkout_attempts")
    op.drop_index(
        "ix_billing_checkout_attempts_requested_by_user_id",
        table_name="billing_checkout_attempts",
    )
    op.drop_index(
        "ix_billing_checkout_attempts_organization_id",
        table_name="billing_checkout_attempts",
    )
    op.drop_index(
        "ix_billing_checkout_attempts_billing_price_id",
        table_name="billing_checkout_attempts",
    )
    op.drop_table("billing_checkout_attempts")
    op.drop_index("ix_billing_prices_plan_id", table_name="billing_prices")
    op.drop_index("ix_billing_prices_catalog", table_name="billing_prices")
    op.drop_table("billing_prices")
    op.drop_index("ix_billing_customers_organization_id", table_name="billing_customers")
    op.drop_table("billing_customers")
    op.drop_column("organizations", "billing_suspended_at")


def _create_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            f"""
            CREATE TRIGGER {_UPDATE_TRIGGER}
            BEFORE UPDATE ON billing_events
            BEGIN
                SELECT RAISE(ABORT, 'billing events are append-only');
            END
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {_DELETE_TRIGGER}
            BEFORE DELETE ON billing_events
            BEGIN
                SELECT RAISE(ABORT, 'billing events are append-only');
            END
            """
        )
        return
    if dialect == "postgresql":
        op.execute(
            f"""
            CREATE FUNCTION {_POSTGRES_FUNCTION}() RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'billing events are append-only';
            END;
            $$
            """
        )
        for trigger, operation in (
            (_UPDATE_TRIGGER, "UPDATE"),
            (_DELETE_TRIGGER, "DELETE"),
        ):
            op.execute(
                f"""
                CREATE TRIGGER {trigger}
                BEFORE {operation} ON billing_events
                FOR EACH ROW EXECUTE FUNCTION {_POSTGRES_FUNCTION}()
                """
            )
        return
    raise RuntimeError(f"Unsupported database dialect for billing protection: {dialect}")


def _drop_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(f"DROP TRIGGER IF EXISTS {_DELETE_TRIGGER}")
        op.execute(f"DROP TRIGGER IF EXISTS {_UPDATE_TRIGGER}")
        return
    if dialect == "postgresql":
        op.execute(f"DROP TRIGGER IF EXISTS {_DELETE_TRIGGER} ON billing_events")
        op.execute(f"DROP TRIGGER IF EXISTS {_UPDATE_TRIGGER} ON billing_events")
        op.execute(f"DROP FUNCTION IF EXISTS {_POSTGRES_FUNCTION}()")
        return
    raise RuntimeError(f"Unsupported database dialect for billing protection: {dialect}")
