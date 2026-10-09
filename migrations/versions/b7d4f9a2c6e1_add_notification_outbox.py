"""add transactional notification outbox

Revision ID: b7d4f9a2c6e1
Revises: a6c3e8f1b4d2
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d4f9a2c6e1"
down_revision: str | None = "a6c3e8f1b4d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
    op.create_index(
        "ix_notification_outboxes_change_id",
        "notification_outboxes",
        ["change_id"],
        unique=True,
    )
    op.create_index(
        "ix_notification_outboxes_idempotency_key",
        "notification_outboxes",
        ["idempotency_key"],
        unique=True,
    )

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
    op.create_index(
        "ix_notification_deliveries_claim",
        "notification_deliveries",
        ["status", "next_attempt_at", "lease_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_notification_deliveries_idempotency_key",
        "notification_deliveries",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_notification_deliveries_outbox_id",
        "notification_deliveries",
        ["outbox_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notification_deliveries_outbox_id", table_name="notification_deliveries")
    op.drop_index(
        "ix_notification_deliveries_idempotency_key",
        table_name="notification_deliveries",
    )
    op.drop_index("ix_notification_deliveries_claim", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index(
        "ix_notification_outboxes_idempotency_key",
        table_name="notification_outboxes",
    )
    op.drop_index("ix_notification_outboxes_change_id", table_name="notification_outboxes")
    op.drop_table("notification_outboxes")
