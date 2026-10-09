"""Separate AI policy and persist fenced ownership of analysis retries.

Revision ID: 7a2d9e4c1b80
Revises: 6f1c8b3e2a90
"""

import sqlalchemy as sa
from alembic import op

revision = "7a2d9e4c1b80"
down_revision = "6f1c8b3e2a90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sites", sa.Column("analysis_mode", sa.String(16), nullable=False, server_default="ai")
    )
    op.add_column(
        "changes",
        sa.Column("analysis_status", sa.String(24), nullable=False, server_default="not_requested"),
    )
    op.add_column("changes", sa.Column("analysis_lease_token", sa.String(36), nullable=True))
    op.add_column(
        "changes", sa.Column("analysis_lease_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        sa.text(
            "UPDATE changes SET analysis_status = CASE "
            "WHEN ai_error IS NOT NULL THEN 'error' "
            "WHEN significant IS NOT NULL THEN 'succeeded' ELSE 'not_requested' END"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("changes") as batch:
        batch.drop_column("analysis_lease_expires_at")
        batch.drop_column("analysis_lease_token")
        batch.drop_column("analysis_status")
    with op.batch_alter_table("sites") as batch:
        batch.drop_column("analysis_mode")
