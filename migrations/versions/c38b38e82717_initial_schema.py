"""Initial schema for Driftwatch 1.0.

The tables, constraints and indexes match the ORM models. The models cannot
express two things, which are added below: the singleton rows that the check
queue and the first-account setup lock against, and the triggers that keep the
audit and billing event ledgers append-only.

This revision replaces the pre-release migration chain. A database created by
that chain is not upgraded; create it again.

Revision ID: c38b38e82717
Revises:
Create Date: 2026-11-13
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c38b38e82717"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("actor_email", sa.String(length=320), nullable=False),
        sa.Column("actor_is_superadmin", sa.Boolean(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=60), nullable=False),
        sa.Column("target_id", sa.String(length=120), nullable=True),
        sa.Column("target_label", sa.String(length=320), nullable=True),
        sa.Column("source_ip", sa.String(length=64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_events_action"), ["action"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_audit_events_actor_user_id"), ["actor_user_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_audit_events_occurred_at"), ["occurred_at"], unique=False
        )
        batch_op.create_index(
            "ix_audit_events_organization_id_id", ["organization_id", "id"], unique=False
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
    with op.batch_alter_table("billing_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_events_event_type"), ["event_type"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_billing_events_occurred_at"), ["occurred_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_billing_events_organization_id"), ["organization_id"], unique=False
        )
        batch_op.create_index(
            "ix_billing_events_received", ["provider", "received_at"], unique=False
        )

    op.create_table(
        "check_queue_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "instance_bootstrap",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_instance_bootstrap_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("max_sites", sa.Integer(), nullable=True),
        sa.Column("max_members", sa.Integer(), nullable=True),
        sa.Column("monthly_ai_check_limit", sa.Integer(), nullable=True),
        sa.Column("price_override_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_self_serve", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("plans", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_plans_key"), ["key"], unique=True)

    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
        sa.UniqueConstraint("key"),
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
    with op.batch_alter_table("billing_event_processing", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_event_processing_status"), ["status"], unique=False
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
    with op.batch_alter_table("billing_prices", schema=None) as batch_op:
        batch_op.create_index(
            "ix_billing_prices_catalog", ["provider", "plan_id", "is_active"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_billing_prices_plan_id"), ["plan_id"], unique=False)

    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("plan", sa.String(length=40), nullable=False),
        sa.Column("max_sites", sa.Integer(), nullable=True),
        sa.Column("max_members", sa.Integer(), nullable=True),
        sa.Column("monthly_ai_check_limit", sa.Integer(), nullable=True),
        sa.Column("site_slots_used", sa.Integer(), nullable=False),
        sa.Column("member_slots_used", sa.Integer(), nullable=False),
        sa.Column("ai_usage_month", sa.String(length=7), nullable=True),
        sa.Column("ai_checks_reserved", sa.Integer(), nullable=False),
        sa.Column("check_queue_claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("billing_suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manually_suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "billing_customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_customer_id", sa.String(length=255), nullable=False),
        sa.Column("terms_version", sa.String(length=80), nullable=True),
        sa.Column("privacy_version", sa.String(length=80), nullable=True),
        sa.Column("terms_sha256", sa.String(length=64), nullable=True),
        sa.Column("privacy_sha256", sa.String(length=64), nullable=True),
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
    with op.batch_alter_table("billing_customers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_customers_organization_id"), ["organization_id"], unique=False
        )

    op.create_table(
        "org_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "key"),
    )
    with op.batch_alter_table("org_settings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_org_settings_organization_id"), ["organization_id"], unique=False
        )

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("notification_mode", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_projects_organization_id"), ["organization_id"], unique=False
        )

    op.create_table(
        "recipients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "email"),
    )
    with op.batch_alter_table("recipients", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_recipients_email"), ["email"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_recipients_organization_id"), ["organization_id"], unique=False
        )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("is_superadmin", sa.Boolean(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("session_generation", sa.String(length=36), nullable=False),
        sa.Column("totp_secret", sa.String(length=255), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), nullable=False),
        sa.Column("pending_totp_nonce", sa.String(length=36), nullable=True),
        sa.Column("totp_last_login_counter", sa.Integer(), nullable=True),
        sa.Column("recovery_code_hashes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)
        batch_op.create_index(
            batch_op.f("ix_users_organization_id"), ["organization_id"], unique=False
        )

    op.create_table(
        "account_email_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("active_key", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt_count >= 0", name="ck_account_email_jobs_attempt_count"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "active_key", name="uq_account_email_jobs_active"),
    )
    with op.batch_alter_table("account_email_jobs", schema=None) as batch_op:
        batch_op.create_index(
            "ix_account_email_jobs_claim",
            ["status", "next_attempt_at", "lease_expires_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_account_email_jobs_idempotency_key"), ["idempotency_key"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_account_email_jobs_organization_id"), ["organization_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_account_email_jobs_user_id"), ["user_id"], unique=False
        )

    op.create_table(
        "billing_checkout_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("billing_price_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("terms_version", sa.String(length=80), nullable=False),
        sa.Column("privacy_version", sa.String(length=80), nullable=False),
        sa.Column("terms_sha256", sa.String(length=64), nullable=True),
        sa.Column("privacy_sha256", sa.String(length=64), nullable=True),
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
        sa.UniqueConstraint("organization_id", "active_marker"),
        sa.UniqueConstraint("organization_id", "idempotency_key"),
    )
    with op.batch_alter_table("billing_checkout_attempts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_checkout_attempts_billing_price_id"),
            ["billing_price_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_checkout_attempts_organization_id"),
            ["organization_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_checkout_attempts_requested_by_user_id"),
            ["requested_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_checkout_attempts_status", ["status", "updated_at"], unique=False
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
    with op.batch_alter_table("billing_subscriptions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_subscriptions_billing_customer_id"),
            ["billing_customer_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_subscriptions_org_status", ["organization_id", "status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_billing_subscriptions_organization_id"),
            ["organization_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_subscriptions_status"), ["status"], unique=False
        )

    op.create_table(
        "project_editors",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "user_id"),
    )
    op.create_table(
        "project_recipients",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["recipients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "recipient_id"),
    )
    op.create_table(
        "sites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("css_selector", sa.String(length=500), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("interaction_steps", sa.JSON(), nullable=False),
        sa.Column("check_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("notification_mode", sa.String(length=32), nullable=True),
        sa.Column("analysis_mode", sa.String(length=16), nullable=False),
        sa.Column("ignore_selectors", sa.JSON(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_alert_code", sa.String(length=40), nullable=True),
        sa.Column("last_alert_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_alert_detail", sa.Text(), nullable=True),
        sa.Column("consecutive_failure_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("sites", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sites_enabled"), ["enabled"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_sites_organization_id"), ["organization_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_sites_project_id"), ["project_id"], unique=False)

    op.create_table(
        "support_access_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("operator_user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("grant_event_id", sa.Integer(), nullable=False),
        sa.Column("active_marker", sa.Boolean(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["grant_event_id"], ["audit_events.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["operator_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grant_event_id"),
        sa.UniqueConstraint("operator_user_id", "organization_id", "active_marker"),
    )
    with op.batch_alter_table("support_access_grants", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_support_access_grants_expires_at"), ["expires_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_support_access_grants_operator_user_id"),
            ["operator_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_support_access_grants_organization_id"),
            ["organization_id"],
            unique=False,
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
    with op.batch_alter_table("billing_entitlement_grants", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_entitlement_grants_organization_id"),
            ["organization_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_entitlement_grants_subscription_id"),
            ["subscription_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_entitlements_org_active", ["organization_id", "is_active"], unique=False
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
    with op.batch_alter_table("billing_invoice_references", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_invoice_references_billing_customer_id"),
            ["billing_customer_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_invoice_references_organization_id"),
            ["organization_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_invoice_references_subscription_id"),
            ["subscription_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_invoices_org_created",
            ["organization_id", "provider_created_at"],
            unique=False,
        )

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
    with op.batch_alter_table("billing_subscription_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_subscription_items_billing_price_id"),
            ["billing_price_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_subscription_items_subscription_id"),
            ["subscription_id"],
            unique=False,
        )

    op.create_table(
        "interaction_secrets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("interaction_secrets", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_interaction_secrets_organization_id"), ["organization_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_interaction_secrets_site_id"), ["site_id"], unique=False
        )

    op.create_table(
        "linked_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.Column("last_modified", sa.String(length=255), nullable=True),
        sa.Column("content_length", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "url"),
    )
    with op.batch_alter_table("linked_assets", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_linked_assets_site_id"), ["site_id"], unique=False)

    op.create_table(
        "recipient_substitutions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("substitute_email", sa.String(length=320), nullable=False),
        sa.Column("substitute_name", sa.String(length=200), nullable=True),
        sa.Column("start_date", sa.String(length=10), nullable=False),
        sa.Column("end_date", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["recipients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("recipient_substitutions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_recipient_substitutions_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_recipient_substitutions_recipient_id"), ["recipient_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_recipient_substitutions_site_id"), ["site_id"], unique=False
        )

    op.create_table(
        "site_check_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("original_job_id", sa.Integer(), nullable=True),
        sa.Column("redrive_request_sha256", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("analyze", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "(source <> 'redrive' AND original_job_id IS NULL AND redrive_request_sha256 IS NULL)"
            " OR (source = 'redrive' AND redrive_request_sha256 IS NOT NULL"
            " AND length(redrive_request_sha256) = 64)",
            name="ck_site_check_jobs_redrive_metadata",
        ),
        sa.CheckConstraint(
            "original_job_id IS NULL OR original_job_id <> id",
            name="ck_site_check_jobs_original_not_self",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["original_job_id"], ["site_check_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("site_check_jobs", schema=None) as batch_op:
        batch_op.create_index(
            "ix_site_check_jobs_active_site",
            ["site_id"],
            unique=True,
            sqlite_where=sa.text("status IN ('pending', 'running')"),
            postgresql_where=sa.text("status IN ('pending', 'running')"),
        )
        batch_op.create_index(
            "ix_site_check_jobs_claim",
            ["status", "available_at", "lease_expires_at", "enqueued_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_site_check_jobs_enqueued_at"), ["enqueued_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_site_check_jobs_idempotency_key"), ["idempotency_key"], unique=True
        )
        batch_op.create_index(
            "ix_site_check_jobs_org_status", ["organization_id", "status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_site_check_jobs_organization_id"), ["organization_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_site_check_jobs_site_id"), ["site_id"], unique=False)
        batch_op.create_index(
            "ux_site_check_jobs_original_job_id",
            ["original_job_id"],
            unique=True,
            sqlite_where=sa.text("original_job_id IS NOT NULL"),
            postgresql_where=sa.text("original_job_id IS NOT NULL"),
        )

    op.create_table(
        "site_editors",
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("site_id", "user_id"),
    )
    op.create_table(
        "site_recipients",
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["recipient_id"], ["recipients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("site_id", "recipient_id"),
    )
    op.create_table(
        "snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("content_html", sa.Text(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("snapshots", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_snapshots_captured_at"), ["captured_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_snapshots_site_id"), ["site_id"], unique=False)

    op.create_table(
        "changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("old_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("new_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("diff_text", sa.Text(), nullable=False),
        sa.Column("diff_html", sa.Text(), nullable=False),
        sa.Column("significant", sa.Boolean(), nullable=True),
        sa.Column("headline", sa.String(length=300), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("ai_error", sa.Text(), nullable=True),
        sa.Column("ai_retry_count", sa.Integer(), nullable=False),
        sa.Column("analysis_status", sa.String(length=24), nullable=False),
        sa.Column("analysis_lease_token", sa.String(length=36), nullable=True),
        sa.Column("analysis_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_verdict", sa.Boolean(), nullable=True),
        sa.Column("user_verdict_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_verdict_user_id", sa.Integer(), nullable=True),
        sa.Column("notification_error", sa.Text(), nullable=True),
        sa.Column("notification_retry_count", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_status", sa.String(length=20), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["new_snapshot_id"],
            ["snapshots.id"],
        ),
        sa.ForeignKeyConstraint(
            ["old_snapshot_id"],
            ["snapshots.id"],
        ),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_verdict_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("changes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_changes_created_at"), ["created_at"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_changes_next_retry_at"), ["next_retry_at"], unique=False
        )
        batch_op.create_index("ix_changes_retry", ["retry_status", "next_retry_at"], unique=False)
        batch_op.create_index("ix_changes_site_created", ["site_id", "created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_changes_site_id"), ["site_id"], unique=False)

    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("change_id", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("pricing_source", sa.String(length=24), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["change_id"], ["changes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("ai_usage", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_ai_usage_created_at"), ["created_at"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_ai_usage_organization_id"), ["organization_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_ai_usage_site_id"), ["site_id"], unique=False)

    op.create_table(
        "notification_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("change_id", sa.Integer(), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["change_id"], ["changes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("notification_log", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_notification_log_change_id"), ["change_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_notification_log_sent_at"), ["sent_at"], unique=False)

    op.create_table(
        "notification_outboxes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("change_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["change_id"], ["changes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("notification_outboxes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_notification_outboxes_change_id"), ["change_id"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_notification_outboxes_idempotency_key"), ["idempotency_key"], unique=True
        )

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("change_id", sa.Integer(), nullable=False),
        sa.Column("significant", sa.Boolean(), nullable=False),
        sa.Column("headline", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("rules_source", sa.String(length=16), nullable=True),
        sa.Column("rules_version", sa.String(length=64), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("input_sha256", sa.String(length=64), nullable=True),
        sa.Column("input_truncated", sa.Boolean(), nullable=True),
        sa.Column("usage_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["change_id"], ["changes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usage_id"], ["ai_usage.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("analysis_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_analysis_runs_change_id"), ["change_id"], unique=False)

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("outbox_id", sa.Integer(), nullable=False),
        sa.Column("destination_key", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("destination_label", sa.String(length=320), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("target_ciphertext", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["outbox_id"], ["notification_outboxes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("outbox_id", "destination_key"),
    )
    with op.batch_alter_table("notification_deliveries", schema=None) as batch_op:
        batch_op.create_index(
            "ix_notification_deliveries_claim",
            ["status", "next_attempt_at", "lease_expires_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_notification_deliveries_idempotency_key"),
            ["idempotency_key"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_notification_deliveries_outbox_id"), ["outbox_id"], unique=False
        )

    op.bulk_insert(
        sa.table(
            "check_queue_state", sa.column("id", sa.Integer), sa.column("updated_at", sa.DateTime)
        ),
        [{"id": 1, "updated_at": datetime.now(UTC)}],
    )
    op.bulk_insert(
        sa.table(
            "instance_bootstrap", sa.column("id", sa.Integer), sa.column("completed", sa.Boolean)
        ),
        [{"id": 1, "completed": False}],
    )
    for table, ledger in _APPEND_ONLY_LEDGERS.items():
        _create_append_only_triggers(table, ledger)


def downgrade() -> None:
    for table, ledger in _APPEND_ONLY_LEDGERS.items():
        _drop_append_only_triggers(table, ledger)
    with op.batch_alter_table("notification_deliveries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notification_deliveries_outbox_id"))
        batch_op.drop_index(batch_op.f("ix_notification_deliveries_idempotency_key"))
        batch_op.drop_index("ix_notification_deliveries_claim")

    op.drop_table("notification_deliveries")
    with op.batch_alter_table("analysis_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_analysis_runs_change_id"))

    op.drop_table("analysis_runs")
    with op.batch_alter_table("notification_outboxes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notification_outboxes_idempotency_key"))
        batch_op.drop_index(batch_op.f("ix_notification_outboxes_change_id"))

    op.drop_table("notification_outboxes")
    with op.batch_alter_table("notification_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notification_log_sent_at"))
        batch_op.drop_index(batch_op.f("ix_notification_log_change_id"))

    op.drop_table("notification_log")
    with op.batch_alter_table("ai_usage", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ai_usage_site_id"))
        batch_op.drop_index(batch_op.f("ix_ai_usage_organization_id"))
        batch_op.drop_index(batch_op.f("ix_ai_usage_created_at"))

    op.drop_table("ai_usage")
    with op.batch_alter_table("changes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_changes_site_id"))
        batch_op.drop_index("ix_changes_site_created")
        batch_op.drop_index("ix_changes_retry")
        batch_op.drop_index(batch_op.f("ix_changes_next_retry_at"))
        batch_op.drop_index(batch_op.f("ix_changes_created_at"))

    op.drop_table("changes")
    with op.batch_alter_table("snapshots", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_snapshots_site_id"))
        batch_op.drop_index(batch_op.f("ix_snapshots_captured_at"))

    op.drop_table("snapshots")
    op.drop_table("site_recipients")
    op.drop_table("site_editors")
    with op.batch_alter_table("site_check_jobs", schema=None) as batch_op:
        batch_op.drop_index(
            "ux_site_check_jobs_original_job_id",
            sqlite_where=sa.text("original_job_id IS NOT NULL"),
            postgresql_where=sa.text("original_job_id IS NOT NULL"),
        )
        batch_op.drop_index(batch_op.f("ix_site_check_jobs_site_id"))
        batch_op.drop_index(batch_op.f("ix_site_check_jobs_organization_id"))
        batch_op.drop_index("ix_site_check_jobs_org_status")
        batch_op.drop_index(batch_op.f("ix_site_check_jobs_idempotency_key"))
        batch_op.drop_index(batch_op.f("ix_site_check_jobs_enqueued_at"))
        batch_op.drop_index("ix_site_check_jobs_claim")
        batch_op.drop_index(
            "ix_site_check_jobs_active_site",
            sqlite_where=sa.text("status IN ('pending', 'running')"),
            postgresql_where=sa.text("status IN ('pending', 'running')"),
        )

    op.drop_table("site_check_jobs")
    with op.batch_alter_table("recipient_substitutions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recipient_substitutions_site_id"))
        batch_op.drop_index(batch_op.f("ix_recipient_substitutions_recipient_id"))
        batch_op.drop_index(batch_op.f("ix_recipient_substitutions_project_id"))

    op.drop_table("recipient_substitutions")
    with op.batch_alter_table("linked_assets", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_linked_assets_site_id"))

    op.drop_table("linked_assets")
    with op.batch_alter_table("interaction_secrets", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_interaction_secrets_site_id"))
        batch_op.drop_index(batch_op.f("ix_interaction_secrets_organization_id"))

    op.drop_table("interaction_secrets")
    with op.batch_alter_table("billing_subscription_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_billing_subscription_items_subscription_id"))
        batch_op.drop_index(batch_op.f("ix_billing_subscription_items_billing_price_id"))

    op.drop_table("billing_subscription_items")
    with op.batch_alter_table("billing_invoice_references", schema=None) as batch_op:
        batch_op.drop_index("ix_billing_invoices_org_created")
        batch_op.drop_index(batch_op.f("ix_billing_invoice_references_subscription_id"))
        batch_op.drop_index(batch_op.f("ix_billing_invoice_references_organization_id"))
        batch_op.drop_index(batch_op.f("ix_billing_invoice_references_billing_customer_id"))

    op.drop_table("billing_invoice_references")
    with op.batch_alter_table("billing_entitlement_grants", schema=None) as batch_op:
        batch_op.drop_index("ix_billing_entitlements_org_active")
        batch_op.drop_index(batch_op.f("ix_billing_entitlement_grants_subscription_id"))
        batch_op.drop_index(batch_op.f("ix_billing_entitlement_grants_organization_id"))

    op.drop_table("billing_entitlement_grants")
    with op.batch_alter_table("support_access_grants", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_support_access_grants_organization_id"))
        batch_op.drop_index(batch_op.f("ix_support_access_grants_operator_user_id"))
        batch_op.drop_index(batch_op.f("ix_support_access_grants_expires_at"))

    op.drop_table("support_access_grants")
    with op.batch_alter_table("sites", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sites_project_id"))
        batch_op.drop_index(batch_op.f("ix_sites_organization_id"))
        batch_op.drop_index(batch_op.f("ix_sites_enabled"))

    op.drop_table("sites")
    op.drop_table("project_recipients")
    op.drop_table("project_editors")
    with op.batch_alter_table("billing_subscriptions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_billing_subscriptions_status"))
        batch_op.drop_index(batch_op.f("ix_billing_subscriptions_organization_id"))
        batch_op.drop_index("ix_billing_subscriptions_org_status")
        batch_op.drop_index(batch_op.f("ix_billing_subscriptions_billing_customer_id"))

    op.drop_table("billing_subscriptions")
    with op.batch_alter_table("billing_checkout_attempts", schema=None) as batch_op:
        batch_op.drop_index("ix_billing_checkout_attempts_status")
        batch_op.drop_index(batch_op.f("ix_billing_checkout_attempts_requested_by_user_id"))
        batch_op.drop_index(batch_op.f("ix_billing_checkout_attempts_organization_id"))
        batch_op.drop_index(batch_op.f("ix_billing_checkout_attempts_billing_price_id"))

    op.drop_table("billing_checkout_attempts")
    with op.batch_alter_table("account_email_jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_account_email_jobs_user_id"))
        batch_op.drop_index(batch_op.f("ix_account_email_jobs_organization_id"))
        batch_op.drop_index(batch_op.f("ix_account_email_jobs_idempotency_key"))
        batch_op.drop_index("ix_account_email_jobs_claim")

    op.drop_table("account_email_jobs")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_organization_id"))
        batch_op.drop_index(batch_op.f("ix_users_email"))

    op.drop_table("users")
    with op.batch_alter_table("recipients", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recipients_organization_id"))
        batch_op.drop_index(batch_op.f("ix_recipients_email"))

    op.drop_table("recipients")
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_projects_organization_id"))

    op.drop_table("projects")
    with op.batch_alter_table("org_settings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_org_settings_organization_id"))

    op.drop_table("org_settings")
    with op.batch_alter_table("billing_customers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_billing_customers_organization_id"))

    op.drop_table("billing_customers")
    op.drop_table("organizations")
    with op.batch_alter_table("billing_prices", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_billing_prices_plan_id"))
        batch_op.drop_index("ix_billing_prices_catalog")

    op.drop_table("billing_prices")
    with op.batch_alter_table("billing_event_processing", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_billing_event_processing_status"))

    op.drop_table("billing_event_processing")
    op.drop_table("settings")
    with op.batch_alter_table("plans", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_plans_key"))

    op.drop_table("plans")
    op.drop_table("instance_bootstrap")
    op.drop_table("check_queue_state")
    with op.batch_alter_table("billing_events", schema=None) as batch_op:
        batch_op.drop_index("ix_billing_events_received")
        batch_op.drop_index(batch_op.f("ix_billing_events_organization_id"))
        batch_op.drop_index(batch_op.f("ix_billing_events_occurred_at"))
        batch_op.drop_index(batch_op.f("ix_billing_events_event_type"))

    op.drop_table("billing_events")
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_events_organization_id_id")
        batch_op.drop_index(batch_op.f("ix_audit_events_occurred_at"))
        batch_op.drop_index(batch_op.f("ix_audit_events_actor_user_id"))
        batch_op.drop_index(batch_op.f("ix_audit_events_action"))

    op.drop_table("audit_events")


@dataclass(frozen=True)
class _Ledger:
    update_trigger: str
    delete_trigger: str
    postgres_function: str
    message: str


# Rows in these tables are evidence; the database itself rejects changes to them.
_APPEND_ONLY_LEDGERS = {
    "audit_events": _Ledger(
        "trg_audit_events_no_update",
        "trg_audit_events_no_delete",
        "driftwatch_reject_audit_event_mutation",
        "audit events are append-only",
    ),
    "billing_events": _Ledger(
        "trg_billing_events_no_update",
        "trg_billing_events_no_delete",
        "driftwatch_reject_billing_event_mutation",
        "billing events are append-only",
    ),
}


def _create_append_only_triggers(table: str, ledger: _Ledger) -> None:
    dialect = op.get_bind().dialect.name
    triggers = ((ledger.update_trigger, "UPDATE"), (ledger.delete_trigger, "DELETE"))
    if dialect == "sqlite":
        for trigger, operation in triggers:
            op.execute(
                f"""
                CREATE TRIGGER {trigger}
                BEFORE {operation} ON {table}
                BEGIN
                    SELECT RAISE(ABORT, '{ledger.message}');
                END
                """
            )
        return
    if dialect == "postgresql":
        op.execute(
            f"""
            CREATE FUNCTION {ledger.postgres_function}() RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION '{ledger.message}';
            END;
            $$
            """
        )
        for trigger, operation in triggers:
            op.execute(
                f"""
                CREATE TRIGGER {trigger}
                BEFORE {operation} ON {table}
                FOR EACH ROW EXECUTE FUNCTION {ledger.postgres_function}()
                """
            )
        return
    raise RuntimeError(f"Unsupported database dialect for {table} protection: {dialect}")


def _drop_append_only_triggers(table: str, ledger: _Ledger) -> None:
    dialect = op.get_bind().dialect.name
    for trigger in (ledger.delete_trigger, ledger.update_trigger):
        suffix = f" ON {table}" if dialect == "postgresql" else ""
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}{suffix}")
    if dialect == "postgresql":
        op.execute(f"DROP FUNCTION IF EXISTS {ledger.postgres_function}()")
