"""add plan is_self_serve flag (public sign-up eligibility)

Revision ID: c9a1f4d7e2b6
Revises: b3f8e2c1a574
Create Date: 2026-06-21 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9a1f4d7e2b6"
down_revision: str | Sequence[str] | None = "b3f8e2c1a574"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("plans", schema=None) as batch_op:
        # Default off: existing plans are not self-serve until the operator opts
        # them in, so no tier becomes publicly self-grantable by this migration.
        batch_op.add_column(
            sa.Column("is_self_serve", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("plans", schema=None) as batch_op:
        batch_op.drop_column("is_self_serve")
