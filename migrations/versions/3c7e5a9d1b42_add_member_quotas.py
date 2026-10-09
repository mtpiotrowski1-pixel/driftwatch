"""add transactional organization member quotas

Revision ID: 3c7e5a9d1b42
Revises: 2b6e4c8a1d50
Create Date: 2026-07-19

Existing member counters are backfilled before the application can reserve new
slots. Legacy bounded public-signup workspaces are capped at their current
membership (or one), preserving every account while closing further free invite
creation until an operator assigns an explicit entitlement.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3c7e5a9d1b42"
down_revision: str | None = "2b6e4c8a1d50"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("max_members", sa.Integer(), nullable=True))
    op.add_column("organizations", sa.Column("max_members", sa.Integer(), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("member_slots_used", sa.Integer(), nullable=False, server_default="0"),
    )

    organizations = sa.table(
        "organizations",
        sa.column("id", sa.Integer()),
        sa.column("plan", sa.String()),
        sa.column("plan_id", sa.Integer()),
        sa.column("max_sites", sa.Integer()),
        sa.column("max_members", sa.Integer()),
        sa.column("monthly_ai_check_limit", sa.Integer()),
        sa.column("member_slots_used", sa.Integer()),
    )
    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("organization_id", sa.Integer()),
        sa.column("is_superadmin", sa.Boolean()),
    )
    member_count = (
        sa.select(sa.func.count(users.c.id))
        .where(
            users.c.organization_id == organizations.c.id,
            users.c.is_superadmin.is_(False),
        )
        .scalar_subquery()
    )
    op.execute(sa.update(organizations).values(member_slots_used=member_count))

    recognized_public_signup = sa.and_(
        organizations.c.plan == "free",
        organizations.c.plan_id.is_(None),
        organizations.c.max_sites == 1,
        organizations.c.monthly_ai_check_limit == 0,
        organizations.c.max_members.is_(None),
    )
    protected_limit = sa.case(
        (organizations.c.member_slots_used > 1, organizations.c.member_slots_used),
        else_=1,
    )
    op.execute(
        sa.update(organizations).where(recognized_public_signup).values(max_members=protected_limit)
    )


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("member_slots_used")
        batch.drop_column("max_members")
    with op.batch_alter_table("plans") as batch:
        batch.drop_column("max_members")
