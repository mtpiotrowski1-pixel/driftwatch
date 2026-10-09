"""separate manual organization suspension from billing state

Revision ID: 5e9a2c7d1f40
Revises: 4d8f1a6c2b70
Create Date: 2026-07-19

An operator suspension must survive later paid subscription events. Existing
inactive organizations without a billing suspension are conservatively treated
as manually suspended during the backfill.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5e9a2c7d1f40"
down_revision: str | None = "4d8f1a6c2b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.add_column(sa.Column("manually_suspended_at", sa.DateTime(timezone=True)))
    op.execute(
        sa.text(
            "UPDATE organizations "
            "SET manually_suspended_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP) "
            "WHERE is_active = false AND billing_suspended_at IS NULL"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("manually_suspended_at")
