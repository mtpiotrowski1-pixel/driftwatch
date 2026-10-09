"""add durable cross-replica site check queue

Revision ID: c8e5a1d3f7b9
Revises: b7d4f9a2c6e1
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8e5a1d3f7b9"
down_revision: str | None = "b7d4f9a2c6e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("check_queue_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "check_queue_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text("INSERT INTO check_queue_state (id, updated_at) VALUES (1, CURRENT_TIMESTAMP)")
    )
    op.create_table(
        "site_check_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_site_check_jobs_active_site",
        "site_check_jobs",
        ["site_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running')"),
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )
    op.create_index(
        "ix_site_check_jobs_claim",
        "site_check_jobs",
        ["status", "available_at", "lease_expires_at", "enqueued_at"],
        unique=False,
    )
    op.create_index(
        "ix_site_check_jobs_enqueued_at",
        "site_check_jobs",
        ["enqueued_at"],
        unique=False,
    )
    op.create_index(
        "ix_site_check_jobs_idempotency_key",
        "site_check_jobs",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_site_check_jobs_org_status",
        "site_check_jobs",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_site_check_jobs_organization_id",
        "site_check_jobs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_site_check_jobs_site_id",
        "site_check_jobs",
        ["site_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_site_check_jobs_site_id", table_name="site_check_jobs")
    op.drop_index("ix_site_check_jobs_organization_id", table_name="site_check_jobs")
    op.drop_index("ix_site_check_jobs_org_status", table_name="site_check_jobs")
    op.drop_index("ix_site_check_jobs_idempotency_key", table_name="site_check_jobs")
    op.drop_index("ix_site_check_jobs_enqueued_at", table_name="site_check_jobs")
    op.drop_index("ix_site_check_jobs_claim", table_name="site_check_jobs")
    op.drop_index("ix_site_check_jobs_active_site", table_name="site_check_jobs")
    op.drop_table("site_check_jobs")
    op.drop_table("check_queue_state")
    op.drop_column("organizations", "check_queue_claimed_at")
