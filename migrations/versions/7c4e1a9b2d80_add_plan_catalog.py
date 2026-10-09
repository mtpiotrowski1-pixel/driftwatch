"""add plan catalog and organization plan link

Revision ID: 7c4e1a9b2d80
Revises: 54eb8a9201c3
Create Date: 2026-06-20 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c4e1a9b2d80"
down_revision: str | Sequence[str] | None = "54eb8a9201c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("max_sites", sa.Integer(), nullable=True),
        sa.Column("monthly_ai_check_limit", sa.Integer(), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plans_key"), "plans", ["key"], unique=True)

    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("plan_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_organizations_plan_id", "plans", ["plan_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.drop_constraint("fk_organizations_plan_id", type_="foreignkey")
        batch_op.drop_column("plan_id")

    op.drop_index(op.f("ix_plans_key"), table_name="plans")
    op.drop_table("plans")
