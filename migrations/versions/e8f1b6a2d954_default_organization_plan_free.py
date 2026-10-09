"""default organization plan 'free' instead of 'trial'

Revision ID: e8f1b6a2d954
Revises: d4b2e8c1f037
Create Date: 2026-07-04 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8f1b6a2d954"
down_revision: str | Sequence[str] | None = "d4b2e8c1f037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Only the column default changes: an organization created without an
    # explicit plan is now labelled 'free' (a self-hosted instance sells
    # nothing, so 'trial' was misleading). Existing rows keep their value.
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.alter_column(
            "plan",
            existing_type=sa.String(length=40),
            server_default="free",
            existing_nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.alter_column(
            "plan",
            existing_type=sa.String(length=40),
            server_default="trial",
            existing_nullable=False,
        )
