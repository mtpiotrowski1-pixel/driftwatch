"""add auditable dead-check redrive lineage

Revision ID: 4d8f1a6c2b70
Revises: 3c7e5a9d1b42
Create Date: 2026-07-19

Redrive creates a new queue row instead of reopening terminal work. The
self-reference preserves that lineage while the original is retained. The
request digest survives retention and lets concurrent or repeated operator
requests distinguish a replay from a conflicting payload.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4d8f1a6c2b70"
down_revision: str | None = "3c7e5a9d1b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("site_check_jobs") as batch:
        batch.add_column(sa.Column("original_job_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("redrive_request_sha256", sa.String(length=64), nullable=True))
        batch.create_foreign_key(
            "fk_site_check_jobs_original_job_id",
            "site_check_jobs",
            ["original_job_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint(
            "ck_site_check_jobs_redrive_metadata",
            "(source <> 'redrive' AND original_job_id IS NULL "
            "AND redrive_request_sha256 IS NULL) OR "
            "(source = 'redrive' AND redrive_request_sha256 IS NOT NULL "
            "AND length(redrive_request_sha256) = 64)",
        )
        batch.create_check_constraint(
            "ck_site_check_jobs_original_not_self",
            "original_job_id IS NULL OR original_job_id <> id",
        )
        batch.create_index(
            "ux_site_check_jobs_original_job_id",
            ["original_job_id"],
            unique=True,
            sqlite_where=sa.text("original_job_id IS NOT NULL"),
            postgresql_where=sa.text("original_job_id IS NOT NULL"),
        )


def downgrade() -> None:
    with op.batch_alter_table("site_check_jobs") as batch:
        batch.drop_index("ux_site_check_jobs_original_job_id")
        batch.drop_constraint(
            "ck_site_check_jobs_original_not_self",
            type_="check",
        )
        batch.drop_constraint(
            "ck_site_check_jobs_redrive_metadata",
            type_="check",
        )
        batch.drop_constraint(
            "fk_site_check_jobs_original_job_id",
            type_="foreignkey",
        )
        batch.drop_column("redrive_request_sha256")
        batch.drop_column("original_job_id")
