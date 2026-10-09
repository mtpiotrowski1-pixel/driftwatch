"""initial schema

Revision ID: ef267a3ce89b
Revises:
Create Date: 2026-06-18 21:21:47.805355

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ef267a3ce89b"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
        sa.UniqueConstraint("key"),
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
        sa.Column("totp_secret", sa.String(length=255), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), nullable=False),
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
        sa.Column("ignore_selectors", sa.JSON(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_alert_code", sa.String(length=40), nullable=True),
        sa.Column("last_alert_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("change_id", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["change_id"], ["changes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("ai_usage", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_ai_usage_created_at"), ["created_at"], unique=False)

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


def downgrade() -> None:
    """Drop the entire schema. This is the base revision, so downgrading deletes
    every table and all data — only meaningful for tearing down a fresh database."""
    with op.batch_alter_table("notification_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notification_log_sent_at"))
        batch_op.drop_index(batch_op.f("ix_notification_log_change_id"))

    op.drop_table("notification_log")
    with op.batch_alter_table("ai_usage", schema=None) as batch_op:
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
    with op.batch_alter_table("recipient_substitutions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recipient_substitutions_site_id"))
        batch_op.drop_index(batch_op.f("ix_recipient_substitutions_recipient_id"))
        batch_op.drop_index(batch_op.f("ix_recipient_substitutions_project_id"))

    op.drop_table("recipient_substitutions")
    with op.batch_alter_table("sites", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sites_project_id"))
        batch_op.drop_index(batch_op.f("ix_sites_organization_id"))
        batch_op.drop_index(batch_op.f("ix_sites_enabled"))

    op.drop_table("sites")
    op.drop_table("project_recipients")
    op.drop_table("project_editors")
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
    op.drop_table("settings")
    op.drop_table("organizations")
