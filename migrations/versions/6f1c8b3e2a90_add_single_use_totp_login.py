"""Persist single-use TOTP login challenges and accepted counters.

Revision ID: 6f1c8b3e2a90
Revises: 5e9a2c7d1f40
"""

import sqlalchemy as sa
from alembic import op

revision = "6f1c8b3e2a90"
down_revision = "5e9a2c7d1f40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("pending_totp_nonce", sa.String(36), nullable=True))
    op.add_column("users", sa.Column("totp_last_login_counter", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("totp_last_login_counter")
        batch.drop_column("pending_totp_nonce")
