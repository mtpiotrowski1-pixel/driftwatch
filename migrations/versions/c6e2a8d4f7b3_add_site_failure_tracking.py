"""add site failure tracking (consecutive count + alert detail)

Revision ID: c6e2a8d4f7b3
Revises: a3d8f5c2b9e1
Create Date: 2026-07-05 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c6e2a8d4f7b3"
down_revision: str | Sequence[str] | None = "a3d8f5c2b9e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("sites") as batch:
        batch.add_column(sa.Column("last_alert_detail", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "consecutive_failure_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("sites") as batch:
        batch.drop_column("consecutive_failure_count")
        batch.drop_column("last_alert_detail")
