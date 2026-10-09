"""add human verdict columns to changes

Revision ID: f2a9c4b7d1e8
Revises: e8f1b6a2d954
Create Date: 2026-07-05 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a9c4b7d1e8"
down_revision: str | Sequence[str] | None = "e8f1b6a2d954"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("changes") as batch:
        batch.add_column(sa.Column("user_verdict", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("user_verdict_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("user_verdict_user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_changes_user_verdict_user_id_users",
            "users",
            ["user_verdict_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("changes") as batch:
        batch.drop_constraint("fk_changes_user_verdict_user_id_users", type_="foreignkey")
        batch.drop_column("user_verdict_user_id")
        batch.drop_column("user_verdict_at")
        batch.drop_column("user_verdict")
