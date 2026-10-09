"""index ai_usage.site_id (usage aggregates join on it)

Revision ID: d4b2e8c1f037
Revises: c9a1f4d7e2b6
Create Date: 2026-06-21 12:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4b2e8c1f037"
down_revision: str | Sequence[str] | None = "c9a1f4d7e2b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(op.f("ix_ai_usage_site_id"), "ai_usage", ["site_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_ai_usage_site_id"), table_name="ai_usage")
