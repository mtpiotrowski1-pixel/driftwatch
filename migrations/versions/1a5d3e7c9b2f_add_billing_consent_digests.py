"""add immutable billing consent document fingerprints

Revision ID: 1a5d3e7c9b2f
Revises: 0f4c2a8d7e31
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1a5d3e7c9b2f"
down_revision: str | None = "0f4c2a8d7e31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("billing_customers") as batch:
        batch.add_column(sa.Column("terms_sha256", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("privacy_sha256", sa.String(length=64), nullable=True))
    with op.batch_alter_table("billing_checkout_attempts") as batch:
        batch.add_column(sa.Column("terms_sha256", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("privacy_sha256", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("billing_checkout_attempts") as batch:
        batch.drop_column("privacy_sha256")
        batch.drop_column("terms_sha256")
    with op.batch_alter_table("billing_customers") as batch:
        batch.drop_column("privacy_sha256")
        batch.drop_column("terms_sha256")
