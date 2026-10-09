"""Record analysis provenance and distinguish unknown costs.

Revision ID: 8b3e0f5d2c91
Revises: 7a2d9e4c1b80
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8b3e0f5d2c91"
down_revision: str | None = "7a2d9e4c1b80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage") as batch:
        batch.alter_column("cost_usd", existing_type=sa.Float(), nullable=True)
        batch.add_column(
            sa.Column("pricing_source", sa.String(24), nullable=False, server_default="legacy")
        )
        batch.add_column(
            sa.Column("purpose", sa.String(16), nullable=False, server_default="change")
        )
    with op.batch_alter_table("analysis_runs") as batch:
        batch.add_column(sa.Column("model", sa.String(80), nullable=True))
        batch.add_column(sa.Column("rules_source", sa.String(16), nullable=True))
        batch.add_column(sa.Column("rules_version", sa.String(64), nullable=True))
        batch.add_column(sa.Column("system_prompt", sa.Text(), nullable=True))
        batch.add_column(sa.Column("input_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("input_truncated", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("usage_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_analysis_runs_usage_id", "ai_usage", ["usage_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    # Downgrading would turn genuinely unknown prices into invented numbers.
    # Refuse a lossy downgrade until those rows have been exported/reconciled.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM ai_usage WHERE cost_usd IS NULL")):
        raise RuntimeError(
            "Cannot downgrade while unknown AI costs exist; preserve or reconcile usage first"
        )
    with op.batch_alter_table("analysis_runs") as batch:
        batch.drop_constraint("fk_analysis_runs_usage_id", type_="foreignkey")
        for name in (
            "usage_id",
            "input_truncated",
            "input_sha256",
            "system_prompt",
            "rules_version",
            "rules_source",
            "model",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("ai_usage") as batch:
        batch.drop_column("purpose")
        batch.drop_column("pricing_source")
        batch.alter_column("cost_usd", existing_type=sa.Float(), nullable=False)
