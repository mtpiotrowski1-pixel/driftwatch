"""protect the audit event ledger from database-level mutation

Revision ID: d0f6b8c2a4e1
Revises: c8e5a1d3f7b9
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d0f6b8c2a4e1"
down_revision: str | None = "c8e5a1d3f7b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPDATE_TRIGGER = "trg_audit_events_no_update"
_DELETE_TRIGGER = "trg_audit_events_no_delete"
_POSTGRES_FUNCTION = "driftwatch_reject_audit_event_mutation"


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            f"""
            CREATE TRIGGER {_UPDATE_TRIGGER}
            BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit events are append-only');
            END
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {_DELETE_TRIGGER}
            BEFORE DELETE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit events are append-only');
            END
            """
        )
        return
    if dialect == "postgresql":
        op.execute(
            f"""
            CREATE FUNCTION {_POSTGRES_FUNCTION}() RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'audit events are append-only';
            END;
            $$
            """
        )
        for trigger in (_UPDATE_TRIGGER, _DELETE_TRIGGER):
            operation = "UPDATE" if trigger == _UPDATE_TRIGGER else "DELETE"
            op.execute(
                f"""
                CREATE TRIGGER {trigger}
                BEFORE {operation} ON audit_events
                FOR EACH ROW EXECUTE FUNCTION {_POSTGRES_FUNCTION}()
                """
            )
        return
    raise RuntimeError(f"Unsupported database dialect for audit protection: {dialect}")


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(f"DROP TRIGGER IF EXISTS {_DELETE_TRIGGER}")
        op.execute(f"DROP TRIGGER IF EXISTS {_UPDATE_TRIGGER}")
        return
    if dialect == "postgresql":
        op.execute(f"DROP TRIGGER IF EXISTS {_DELETE_TRIGGER} ON audit_events")
        op.execute(f"DROP TRIGGER IF EXISTS {_UPDATE_TRIGGER} ON audit_events")
        op.execute(f"DROP FUNCTION IF EXISTS {_POSTGRES_FUNCTION}()")
        return
    raise RuntimeError(f"Unsupported database dialect for audit protection: {dialect}")
