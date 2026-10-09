"""make plan price an optional override (NULL follows the algorithm)

Revision ID: b3f8e2c1a574
Revises: 7c4e1a9b2d80
Create Date: 2026-06-21 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f8e2c1a574"
down_revision: str | Sequence[str] | None = "7c4e1a9b2d80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("plans", schema=None) as batch_op:
        batch_op.alter_column(
            "price_cents",
            new_column_name="price_override_cents",
            existing_type=sa.Integer(),
            nullable=True,
            existing_server_default=sa.text("'0'"),
            server_default=None,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("plans", schema=None) as batch_op:
        batch_op.alter_column(
            "price_override_cents",
            new_column_name="price_cents",
            existing_type=sa.Integer(),
            nullable=False,
            server_default=sa.text("'0'"),
        )
