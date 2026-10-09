"""add encrypted vault for interaction fill values

Revision ID: e1c7a4b9d2f6
Revises: d9f4b1e7a2c5
Create Date: 2026-07-17 12:00:00.000000

Historical fill values cannot be safely encrypted here because Alembic does
not receive the application's encryption key. The fail-safe migration removes
those fill steps and strips all legacy value-bearing fields from other steps.
Operators must re-enter removed fill values after the upgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1c7a4b9d2f6"
down_revision: str | Sequence[str] | None = "d9f4b1e7a2c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SAFE_ACTIONS = frozenset({"click", "wait_for", "wait"})


def upgrade() -> None:
    op.create_table(
        "interaction_secrets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_interaction_secrets_organization_id"),
        "interaction_secrets",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_interaction_secrets_site_id"),
        "interaction_secrets",
        ["site_id"],
        unique=False,
    )
    _remove_fill_steps()


def downgrade() -> None:
    # Old application versions understand only plaintext ``value``. Remove
    # reference-only fills before dropping their vault so rollback fails closed.
    _remove_fill_steps()
    op.drop_index(op.f("ix_interaction_secrets_site_id"), table_name="interaction_secrets")
    op.drop_index(op.f("ix_interaction_secrets_organization_id"), table_name="interaction_secrets")
    op.drop_table("interaction_secrets")


def _remove_fill_steps() -> None:
    sites = sa.table(
        "sites",
        sa.column("id", sa.Integer()),
        sa.column("interaction_steps", sa.JSON()),
    )
    connection = op.get_bind()
    # SQLite may otherwise leave shortened JSON payloads in free page space,
    # which its online-backup API would faithfully copy. Secure-delete makes
    # this logical redaction effective for newly generated backups as well.
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA secure_delete=ON")
    rows = connection.execute(sa.select(sites.c.id, sites.c.interaction_steps)).mappings()
    for row in rows:
        raw_steps = row["interaction_steps"]
        safe_steps: list[dict[str, object]] = []
        if isinstance(raw_steps, list):
            for raw in raw_steps:
                if not isinstance(raw, dict) or raw.get("action") not in _SAFE_ACTIONS:
                    continue
                safe_steps.append(
                    {
                        "action": raw["action"],
                        "selector": raw.get("selector"),
                        "timeout_ms": raw.get("timeout_ms", 10_000),
                    }
                )
        if safe_steps != raw_steps:
            connection.execute(
                sa.update(sites).where(sites.c.id == row["id"]).values(interaction_steps=safe_steps)
            )
