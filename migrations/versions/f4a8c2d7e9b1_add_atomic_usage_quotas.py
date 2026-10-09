"""add immutable usage ownership and transactional quota counters

Revision ID: f4a8c2d7e9b1
Revises: e1c7a4b9d2f6
Create Date: 2026-07-17 15:00:00.000000

Usage ownership is backfilled from the current site, or from the usage row's
change and that change's current site. The migration stops before schema changes
when historical rows cannot be attributed reliably; billing/cost evidence must
never be deleted merely to satisfy a new constraint.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4a8c2d7e9b1"
down_revision: str | Sequence[str] | None = "e1c7a4b9d2f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    unattributed = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT count(*)
            FROM ai_usage AS usage
            LEFT JOIN sites AS direct_site ON direct_site.id = usage.site_id
            LEFT JOIN changes AS usage_change ON usage_change.id = usage.change_id
            LEFT JOIN sites AS change_site ON change_site.id = usage_change.site_id
            WHERE COALESCE(direct_site.organization_id, change_site.organization_id) IS NULL
            """
            )
        )
        .scalar_one()
    )
    if unattributed:
        raise RuntimeError(
            "Cannot add immutable AI usage ownership: "
            f"{unattributed} historical ai_usage row(s) have no attributable organization. "
            "Restore the missing ownership from a verified backup or archive and remediate "
            "those rows explicitly before retrying; the migration will not delete them."
        )

    op.add_column(
        "organizations",
        sa.Column("site_slots_used", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("organizations", sa.Column("ai_usage_month", sa.String(length=7)))
    op.add_column(
        "organizations",
        sa.Column("ai_checks_reserved", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        sa.text(
            "UPDATE organizations SET site_slots_used = "
            "(SELECT count(*) FROM sites WHERE sites.organization_id = organizations.id)"
        )
    )

    op.add_column("ai_usage", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE ai_usage SET organization_id = "
            "COALESCE("
            "(SELECT sites.organization_id FROM sites WHERE sites.id = ai_usage.site_id), "
            "(SELECT sites.organization_id FROM changes "
            "JOIN sites ON sites.id = changes.site_id "
            "WHERE changes.id = ai_usage.change_id)"
            ")"
        )
    )
    with op.batch_alter_table("ai_usage") as batch:
        batch.alter_column("organization_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            "fk_ai_usage_organization_id_organizations",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_index("ix_ai_usage_organization_id", ["organization_id"])


def downgrade() -> None:
    with op.batch_alter_table("ai_usage") as batch:
        batch.drop_index("ix_ai_usage_organization_id")
        batch.drop_constraint(
            "fk_ai_usage_organization_id_organizations",
            type_="foreignkey",
        )
        batch.drop_column("organization_id")
    op.drop_column("organizations", "ai_checks_reserved")
    op.drop_column("organizations", "ai_usage_month")
    op.drop_column("organizations", "site_slots_used")
