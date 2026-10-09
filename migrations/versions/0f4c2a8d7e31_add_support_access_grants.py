"""add server-authoritative support access grants

Revision ID: 0f4c2a8d7e31
Revises: f3b9d6e1a4c8
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0f4c2a8d7e31"
down_revision: str | None = "f3b9d6e1a4c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
        sa.ForeignKeyConstraint(
            ["grant_event_id"],
            ["audit_events.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["operator_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operator_user_id", "organization_id", "active_marker"),
        sa.UniqueConstraint("grant_event_id"),
    )
    op.create_index(
        "ix_support_access_grants_expires_at",
        "support_access_grants",
        ["expires_at"],
    )
    op.create_index(
        "ix_support_access_grants_operator_user_id",
        "support_access_grants",
        ["operator_user_id"],
    )
    op.create_index(
        "ix_support_access_grants_organization_id",
        "support_access_grants",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_support_access_grants_organization_id",
        table_name="support_access_grants",
    )
    op.drop_index(
        "ix_support_access_grants_operator_user_id",
        table_name="support_access_grants",
    )
    op.drop_index(
        "ix_support_access_grants_expires_at",
        table_name="support_access_grants",
    )
    op.drop_table("support_access_grants")
