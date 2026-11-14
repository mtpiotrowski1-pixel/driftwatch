"""The Alembic baseline builds exactly the schema the models describe.

Tests and the application both create their schema through the migrations, so a
model change without a matching migration fails here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from driftwatch.db import Base, Database, _alembic_paths, _run_migrations
from driftwatch.models import AuditEvent, BillingEvent


def _config(url: str) -> Config:
    alembic_ini, migrations_dir = _alembic_paths()
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(migrations_dir))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _drift_from_models(url: str) -> list[object]:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            return list(compare_metadata(context, Base.metadata))
    finally:
        engine.dispose()


def test_migrated_schema_matches_models(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    _run_migrations(url)

    assert _drift_from_models(url) == []


def test_baseline_downgrades_to_an_empty_database_and_upgrades_again(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'round-trip.db'}"
    config = _config(url)
    command.upgrade(config, "head")

    command.downgrade(config, "base")
    engine = create_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
        with engine.connect() as connection:
            triggers = connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            ).all()
        assert triggers == []
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    assert _drift_from_models(url) == []


def test_baseline_creates_the_singleton_rows(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'singletons.db'}"
    _run_migrations(url)

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            queue = connection.exec_driver_sql("SELECT id FROM check_queue_state").all()
            bootstrap = connection.exec_driver_sql(
                "SELECT id, completed FROM instance_bootstrap"
            ).all()
    finally:
        engine.dispose()

    assert queue == [(1,)]
    assert bootstrap == [(1, 0)]


def _audit_event() -> AuditEvent:
    return AuditEvent(
        actor_user_id=1,
        actor_email="operator@example.test",
        actor_is_superadmin=True,
        action="test.created",
        target_type="test",
        details={},
    )


def _billing_event() -> BillingEvent:
    return BillingEvent(
        provider="stripe",
        provider_event_id="evt_ledger_test",
        event_type="invoice.paid",
        occurred_at=datetime.now(UTC),
        payload_sha256="0" * 64,
    )


@pytest.mark.parametrize(
    ("table", "build_row"),
    [("audit_events", _audit_event), ("billing_events", _billing_event)],
)
def test_event_ledgers_are_append_only_at_database_level(
    tmp_path: Path, table: str, build_row: Callable[[], object]
) -> None:
    url = f"sqlite:///{tmp_path / 'ledger.db'}"
    _run_migrations(url)

    engine = create_engine(url)
    try:
        with Session(engine) as session:
            session.add(build_row())
            session.commit()

        # Raw SQL bypasses the ORM guards, so only the database triggers stop it.
        with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
            connection.exec_driver_sql(f"UPDATE {table} SET id = id WHERE id = 1")
        with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
            connection.exec_driver_sql(f"DELETE FROM {table} WHERE id = 1")

        with engine.connect() as connection:
            assert connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one() == 1
    finally:
        engine.dispose()


def test_unversioned_schema_from_the_models_is_never_stamped_to_head(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'current-unversioned.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()

    with pytest.raises(RuntimeError, match="without Alembic provenance"):
        _run_migrations(url)

    engine = create_engine(url)
    try:
        assert not inspect(engine).has_table("alembic_version")
    finally:
        engine.dispose()


def test_partial_unversioned_schema_is_never_stamped_to_head(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'partial-unversioned.db'}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    engine.dispose()

    with pytest.raises(RuntimeError, match="without Alembic provenance"):
        _run_migrations(url)

    engine = create_engine(url)
    try:
        assert not inspect(engine).has_table("alembic_version")
    finally:
        engine.dispose()


async def test_disabled_runtime_migrations_require_the_exact_head(tmp_path: Path) -> None:
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'release-phase.db'}")
    try:
        with pytest.raises(RuntimeError, match="not at the required Alembic head"):
            await db.require_migration_head()

        await db.upgrade()
        await db.require_migration_head()
    finally:
        await db.dispose()
