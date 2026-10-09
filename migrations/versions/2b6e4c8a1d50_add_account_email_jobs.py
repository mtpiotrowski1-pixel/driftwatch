"""add durable account email jobs

Revision ID: 2b6e4c8a1d50
Revises: 1a5d3e7c9b2f
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2b6e4c8a1d50"
down_revision: str | None = "1a5d3e7c9b2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
    op.create_index(
        "ix_account_email_jobs_claim",
        "account_email_jobs",
        ["status", "next_attempt_at", "lease_expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_email_jobs_idempotency_key"),
        "account_email_jobs",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_account_email_jobs_organization_id"),
        "account_email_jobs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_email_jobs_user_id"),
        "account_email_jobs",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_account_email_jobs_user_id"), table_name="account_email_jobs")
    op.drop_index(op.f("ix_account_email_jobs_organization_id"), table_name="account_email_jobs")
    op.drop_index(op.f("ix_account_email_jobs_idempotency_key"), table_name="account_email_jobs")
    op.drop_index("ix_account_email_jobs_claim", table_name="account_email_jobs")
    op.drop_table("account_email_jobs")
