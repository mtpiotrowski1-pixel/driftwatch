"""Alembic environment.

Migrations run synchronously, so an async driver URL (``+aiosqlite`` /
``+asyncpg``) is mapped to its synchronous peer. The URL is taken from the
Alembic config when the application drives the upgrade, and otherwise falls back
to the application's own settings so ``alembic`` CLI commands work without extra
configuration.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from driftwatch import models  # noqa: F401  (registers every table on Base.metadata)
from driftwatch.config import get_settings
from driftwatch.db import Base, sync_database_url

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    return configured or sync_database_url(get_settings().database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    # Batch mode lets SQLite emulate the ALTERs it lacks by rebuilding tables.
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
