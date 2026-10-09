"""The Alembic migrations must build exactly the schema the models describe.

The application runs migrations in production but builds the schema directly from
the models in tests (for speed). This guard keeps the two paths from drifting: a
new column or index on a model without a matching migration fails here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, inspect
from sqlalchemy.exc import DBAPIError

from driftwatch import models
from driftwatch.db import Base, Database, _alembic_paths, _run_migrations, snapshot_sqlite


def _schema(url: str) -> dict[str, tuple[frozenset[str], frozenset[tuple[str, ...]]]]:
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        return {
            table: (
                frozenset(col["name"] for col in inspector.get_columns(table)),
                frozenset(tuple(idx["column_names"]) for idx in inspector.get_indexes(table)),
            )
            for table in inspector.get_table_names()
            if table != "alembic_version"  # Alembic's own bookkeeping, not a model
        }
    finally:
        engine.dispose()


def test_initial_migration_matches_models(tmp_path: Path) -> None:
    migrated = tmp_path / "migrated.db"
    from_models = tmp_path / "from_models.db"

    _run_migrations(f"sqlite:///{migrated}")

    engine = create_engine(f"sqlite:///{from_models}")
    Base.metadata.create_all(engine)
    engine.dispose()

    assert _schema(f"sqlite:///{migrated}") == _schema(f"sqlite:///{from_models}")


@pytest.mark.parametrize("existing_table", ["users", "organizations"])
def test_initial_admin_migration_closes_existing_installations(
    tmp_path: Path, existing_table: str
) -> None:
    url = f"sqlite:///{tmp_path / 'legacy-ownership.db'}"
    alembic_ini, migrations_dir = _alembic_paths()
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(migrations_dir))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "8b3e0f5d2c91")
    engine = create_engine(url)
    with engine.begin() as connection:
        if existing_table == "users":
            connection.execute(
                models.User.__table__.insert().values(
                    email="legacy-member@example.test",
                    password_hash="unused-test-hash",
                    is_admin=False,
                    is_superadmin=False,
                )
            )
        else:
            connection.execute(
                models.Organization.__table__.insert().values(name="Existing workspace")
            )
    command.upgrade(config, "head")
    with engine.begin() as connection:
        assert connection.execute(models.InstanceBootstrap.__table__.select()).one() == (1, True)
        if existing_table == "users":
            member = connection.execute(models.User.__table__.select()).mappings().one()
            assert member["is_admin"] is False
            assert member["is_superadmin"] is False
        connection.execute(Base.metadata.tables[existing_table].delete())
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(models.InstanceBootstrap.__table__.select()).one() == (1, True)
    engine.dispose()


def test_current_unversioned_schema_is_never_stamped_to_head(tmp_path: Path) -> None:
    database = tmp_path / "current-unversioned.db"
    url = f"sqlite:///{database}"
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


async def test_disabled_runtime_migrations_require_the_exact_head(tmp_path: Path) -> None:
    database = tmp_path / "release-phase.db"
    db = Database(f"sqlite+aiosqlite:///{database}")
    try:
        with pytest.raises(RuntimeError, match="not at the required Alembic head"):
            await db.require_migration_head()

        await db.upgrade()
        await db.require_migration_head()
    finally:
        await db.dispose()


def test_account_email_queue_migration_is_reversible(tmp_path: Path) -> None:
    database = tmp_path / "account-mail-reversible.db"
    url = f"sqlite:///{database}"
    alembic_ini, migrations_dir = _alembic_paths()
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(migrations_dir))
    config.set_main_option("sqlalchemy.url", url)

    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        assert inspect(engine).has_table("account_email_jobs")
    finally:
        engine.dispose()

    command.downgrade(config, "1a5d3e7c9b2f")
    engine = create_engine(url)
    try:
        assert not inspect(engine).has_table("account_email_jobs")
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        assert inspect(engine).has_table("account_email_jobs")
    finally:
        engine.dispose()


def test_member_quota_migration_backfills_and_bounds_legacy_signup_org(
    tmp_path: Path,
) -> None:
    database = tmp_path / "member-quota-backfill.db"
    url = f"sqlite:///{database}"
    alembic_ini, migrations_dir = _alembic_paths()
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(migrations_dir))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "2b6e4c8a1d50")

    engine = create_engine(url)
    metadata = MetaData()
    organizations = Table("organizations", metadata, autoload_with=engine)
    users = Table("users", metadata, autoload_with=engine)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        organization_id = connection.execute(
            organizations.insert().values(
                name="Legacy public signup",
                is_active=True,
                created_at=now,
                updated_at=now,
                plan="free",
                max_sites=1,
                monthly_ai_check_limit=0,
            )
        ).inserted_primary_key[0]
        connection.execute(
            users.insert(),
            [
                {
                    "email": f"legacy-member-{index}@example.test",
                    "password_hash": "unusable-test-hash",
                    "organization_id": organization_id,
                    "is_superadmin": False,
                    "is_admin": index == 0,
                    "is_active": True,
                    "token_version": 0,
                    "totp_enabled": False,
                    "recovery_code_hashes": [],
                    "created_at": now,
                    "session_generation": str(uuid4()),
                }
                for index in range(2)
            ],
        )
        connection.execute(
            users.insert().values(
                email="legacy-operator@example.test",
                password_hash="unusable-test-hash",
                organization_id=organization_id,
                is_superadmin=True,
                is_admin=True,
                is_active=True,
                token_version=0,
                totp_enabled=False,
                recovery_code_hashes=[],
                created_at=now,
                session_generation=str(uuid4()),
            )
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        columns = {column["name"] for column in inspect(engine).get_columns("organizations")}
        plan_columns = {column["name"] for column in inspect(engine).get_columns("plans")}
        with engine.connect() as connection:
            quota = connection.exec_driver_sql(
                "SELECT max_members, member_slots_used FROM organizations WHERE id = ?",
                (organization_id,),
            ).one()
        assert {"max_members", "member_slots_used"} <= columns
        assert "max_members" in plan_columns
        assert tuple(quota) == (2, 2)
    finally:
        engine.dispose()

    command.downgrade(config, "2b6e4c8a1d50")
    engine = create_engine(url)
    try:
        assert "max_members" not in {
            column["name"] for column in inspect(engine).get_columns("organizations")
        }
        assert "member_slots_used" not in {
            column["name"] for column in inspect(engine).get_columns("organizations")
        }
        assert "max_members" not in {
            column["name"] for column in inspect(engine).get_columns("plans")
        }
    finally:
        engine.dispose()


def test_dead_check_redrive_migration_is_reversible(tmp_path: Path) -> None:
    database = tmp_path / "dead-check-redrive-reversible.db"
    url = f"sqlite:///{database}"
    alembic_ini, migrations_dir = _alembic_paths()
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(migrations_dir))
    config.set_main_option("sqlalchemy.url", url)

    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        columns = {column["name"] for column in inspect(engine).get_columns("site_check_jobs")}
        indexes = {index["name"]: index for index in inspect(engine).get_indexes("site_check_jobs")}
        assert {"original_job_id", "redrive_request_sha256"} <= columns
        assert indexes["ux_site_check_jobs_original_job_id"]["unique"] == 1
    finally:
        engine.dispose()

    command.downgrade(config, "3c7e5a9d1b42")
    engine = create_engine(url)
    try:
        columns = {column["name"] for column in inspect(engine).get_columns("site_check_jobs")}
        assert "original_job_id" not in columns
        assert "redrive_request_sha256" not in columns
    finally:
        engine.dispose()

    command.upgrade(config, "head")


def test_audit_event_ledger_is_append_only_at_database_level(tmp_path: Path) -> None:
    database = tmp_path / "audit-ledger.db"
    url = f"sqlite:///{database}"
    _run_migrations(url)

    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO audit_events (
                    occurred_at, actor_user_id, actor_email, actor_is_superadmin,
                    organization_id, action, target_type, target_id, target_label,
                    source_ip, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat(),
                    1,
                    "operator@example.test",
                    True,
                    None,
                    "test.created",
                    "test",
                    "1",
                    "immutable",
                    "127.0.0.1",
                    "{}",
                ),
            )

        with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE audit_events SET action = 'test.changed' WHERE id = 1"
            )
        with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
            connection.exec_driver_sql("DELETE FROM audit_events WHERE id = 1")

        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM audit_events").scalar_one() == 1
    finally:
        engine.dispose()


def test_partial_unversioned_schema_is_never_stamped_to_head(tmp_path: Path) -> None:
    database = tmp_path / "partial-unversioned.db"
    url = f"sqlite:///{database}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    engine.dispose()

    try:
        _run_migrations(url)
    except RuntimeError as exc:
        assert "without Alembic provenance" in str(exc)
    else:
        raise AssertionError("an unknown unversioned schema was accepted")

    engine = create_engine(url)
    try:
        assert not inspect(engine).has_table("alembic_version")
    finally:
        engine.dispose()


def test_usage_ownership_migration_preserves_unattributed_history(tmp_path: Path) -> None:
    database = tmp_path / "unattributed-usage.db"
    url = f"sqlite:///{database}"
    alembic_ini, migrations_dir = _alembic_paths()
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(migrations_dir))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "e1c7a4b9d2f6")

    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO ai_usage (
                    site_id, change_id, model, prompt_tokens, completion_tokens,
                    total_tokens, cost_usd, created_at
                ) VALUES (NULL, NULL, 'legacy-model', 10, 5, 15, 0.01, ?)
                """,
                (datetime.now(UTC).isoformat(),),
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="will not delete them"):
        command.upgrade(config, "head")

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM ai_usage").scalar_one() == 1
            assert (
                connection.exec_driver_sql("SELECT model FROM ai_usage").scalar_one()
                == "legacy-model"
            )
    finally:
        engine.dispose()


def test_interaction_vault_migration_removes_historical_plaintext(tmp_path: Path) -> None:
    database = tmp_path / "historical.db"
    url = f"sqlite:///{database}"
    alembic_ini, migrations_dir = _alembic_paths()
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(migrations_dir))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "d9f4b1e7a2c5")

    engine = create_engine(url)
    metadata = MetaData()
    organizations = Table("organizations", metadata, autoload_with=engine)
    sites = Table("sites", metadata, autoload_with=engine)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        organization_id = connection.execute(
            organizations.insert().values(
                name="Historical",
                is_active=True,
                plan="free",
                created_at=now,
                updated_at=now,
            )
        ).inserted_primary_key[0]
        site_id = connection.execute(
            sites.insert().values(
                organization_id=organization_id,
                url="https://example.test",
                interaction_steps=[
                    {
                        "action": "fill",
                        "selector": "#token",
                        "value": "legacy-plaintext-secret",
                        "timeout_ms": 10_000,
                    },
                    {
                        "action": "click",
                        "selector": "#submit",
                        "value": "unexpected-sensitive-field",
                        "timeout_ms": 10_000,
                    },
                ],
                check_interval_minutes=60,
                enabled=True,
                ignore_selectors=[],
                created_at=now,
                updated_at=now,
            )
        ).inserted_primary_key[0]
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(url)
    with engine.connect() as connection:
        steps = connection.exec_driver_sql(
            "SELECT interaction_steps FROM sites WHERE id = ?", (site_id,)
        ).scalar_one()
        vault_count = connection.exec_driver_sql(
            "SELECT count(*) FROM interaction_secrets"
        ).scalar_one()
    engine.dispose()

    assert "legacy-plaintext-secret" not in steps
    assert "unexpected-sensitive-field" not in steps
    assert "fill" not in steps
    assert '"action": "click"' in steps
    assert vault_count == 0

    backup = tmp_path / "historical-backup.db"
    snapshot_sqlite(database, backup)
    assert b"legacy-plaintext-secret" not in backup.read_bytes()
    assert b"unexpected-sensitive-field" not in backup.read_bytes()


def test_session_generation_migration_is_reversible_and_unique(tmp_path: Path) -> None:
    database = tmp_path / "session-generation.db"
    url = f"sqlite:///{database}"
    alembic_ini, migrations_dir = _alembic_paths()
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(migrations_dir))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "e2f7c9a4b6d1")

    engine = create_engine(url)
    now = datetime.now(UTC).isoformat()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO organizations (
                name, is_active, plan, max_sites, monthly_ai_check_limit,
                site_slots_used, ai_usage_month, ai_checks_reserved,
                check_queue_claimed_at, billing_suspended_at, plan_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("Auth migration", True, "free", 1, 0, 0, None, 0, None, None, None, now, now),
        )
        for index in range(2):
            connection.exec_driver_sql(
                """
                INSERT INTO users (
                    email, name, password_hash, organization_id, is_superadmin,
                    is_admin, is_active, token_version, totp_secret, totp_enabled,
                    recovery_code_hashes, created_at, last_login_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"user{index}@example.test",
                    None,
                    "hash",
                    1,
                    False,
                    False,
                    True,
                    0,
                    None,
                    False,
                    "[]",
                    now,
                    None,
                ),
            )
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(url)
    with engine.connect() as connection:
        first_generations = list(
            connection.exec_driver_sql("SELECT session_generation FROM users ORDER BY id").scalars()
        )
        support_columns = {
            column["name"] for column in inspect(connection).get_columns("support_access_grants")
        }
        support_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspect(connection).get_unique_constraints("support_access_grants")
        }
    engine.dispose()
    assert len(set(first_generations)) == 2
    assert all(str(UUID(value)) == value for value in first_generations)
    assert "active_marker" in support_columns
    assert ("operator_user_id", "organization_id", "active_marker") in support_uniques

    command.downgrade(config, "e2f7c9a4b6d1")
    engine = create_engine(url)
    try:
        assert "session_generation" not in {
            column["name"] for column in inspect(engine).get_columns("users")
        }
        assert "support_access_grants" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(url)
    with engine.connect() as connection:
        second_generations = list(
            connection.exec_driver_sql("SELECT session_generation FROM users ORDER BY id").scalars()
        )
        assert "support_access_grants" in inspect(connection).get_table_names()
    engine.dispose()
    assert len(set(second_generations)) == 2
    assert first_generations != second_generations


def test_manual_suspension_migration_backfills_and_is_reversible(tmp_path: Path) -> None:
    database = tmp_path / "manual-suspension.db"
    url = f"sqlite:///{database}"
    alembic_ini, migrations_dir = _alembic_paths()
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(migrations_dir))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "4d8f1a6c2b70")

    engine = create_engine(url)
    metadata = MetaData()
    organizations = Table("organizations", metadata, autoload_with=engine)
    now = datetime.now(UTC)

    def organization_values(name: str, *, active: bool, billing: bool) -> dict[str, object]:
        return {
            "name": name,
            "is_active": active,
            "plan": "free",
            "site_slots_used": 0,
            "member_slots_used": 0,
            "ai_checks_reserved": 0,
            "billing_suspended_at": now if billing else None,
            "created_at": now,
            "updated_at": now,
        }

    with engine.begin() as connection:
        connection.execute(
            organizations.insert(),
            [
                organization_values("Active", active=True, billing=False),
                organization_values("Manual", active=False, billing=False),
                organization_values("Billing", active=False, billing=True),
            ],
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(url)
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT name, manually_suspended_at FROM organizations ORDER BY id"
        ).all()
    engine.dispose()
    assert rows[0][1] is None
    assert rows[1][1] is not None
    assert rows[2][1] is None

    command.downgrade(config, "4d8f1a6c2b70")
    engine = create_engine(url)
    try:
        assert "manually_suspended_at" not in {
            column["name"] for column in inspect(engine).get_columns("organizations")
        }
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        assert "manually_suspended_at" in {
            column["name"] for column in inspect(engine).get_columns("organizations")
        }
    finally:
        engine.dispose()
