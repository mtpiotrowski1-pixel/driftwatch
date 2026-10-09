"""bind authentication tokens to a non-reusable user generation

Revision ID: f3b9d6e1a4c8
Revises: e2f7c9a4b6d1
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "f3b9d6e1a4c8"
down_revision: str | None = "e2f7c9a4b6d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_generation", sa.String(length=36), nullable=True),
    )
    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("session_generation", sa.String(length=36)),
    )
    connection = op.get_bind()
    user_ids = list(connection.execute(sa.select(users.c.id)).scalars())
    if user_ids:
        connection.execute(
            users.update()
            .where(users.c.id == sa.bindparam("user_id"))
            .values(session_generation=sa.bindparam("generation")),
            [{"user_id": user_id, "generation": str(uuid4())} for user_id in user_ids],
        )
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "session_generation",
            existing_type=sa.String(length=36),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("session_generation")
