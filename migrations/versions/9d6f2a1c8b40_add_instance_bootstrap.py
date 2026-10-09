"""Persist the one-time initial administrator claim.

Revision ID: 9d6f2a1c8b40
Revises: 8b3e0f5d2c91
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d6f2a1c8b40"
down_revision: str | None = "8b3e0f5d2c91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bootstrap = op.create_table(
        "instance_bootstrap",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_instance_bootstrap_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    # An existing organization also closes the claim if its users were removed.
    connection = op.get_bind()
    occupied = connection.scalar(
        sa.select(
            sa.exists(sa.select(sa.literal(1)).select_from(sa.table("users")))
            | sa.exists(sa.select(sa.literal(1)).select_from(sa.table("organizations")))
        )
    )
    connection.execute(bootstrap.insert().values(id=1, completed=bool(occupied)))


def downgrade() -> None:
    op.drop_table("instance_bootstrap")
