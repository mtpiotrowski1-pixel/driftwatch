"""Async database engine, session factory, and the declarative base.

SQLite is the default backend; ``DATABASE_URL`` may point at Postgres instead.
For SQLite we enable foreign-key enforcement (off by default, and what makes
``ON DELETE CASCADE`` fire) and switch to WAL journaling so the dashboard's
reads don't serialize against the scheduler's writes during long uptimes.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, closing
from pathlib import Path

from alembic.config import Config
from anyio import to_thread
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from driftwatch.config import PROJECT_ROOT

# Tables a restored snapshot must contain to be plausibly this application's
# database — a cheap guard against importing a truncated or foreign file.
_REQUIRED_TABLES = frozenset({"organizations", "users", "sites"})


def _alembic_paths() -> tuple[Path, Path]:
    """Locate ``alembic.ini`` and the ``migrations`` directory.

    In the source tree they sit at the project root. ``pip install`` does not
    package the repo-root migrations, so the Docker image copies them next to the
    app's working directory instead — fall back to the current directory when the
    installed layout puts ``PROJECT_ROOT`` outside the project (site-packages)."""
    for base in (PROJECT_ROOT, Path.cwd()):
        migrations = base / "migrations"
        if (migrations / "env.py").exists():
            return base / "alembic.ini", migrations
    return PROJECT_ROOT / "alembic.ini", PROJECT_ROOT / "migrations"


class Base(DeclarativeBase):
    pass


def create_engine(database_url: str) -> AsyncEngine:
    if database_url.startswith("sqlite"):
        engine = create_async_engine(database_url, future=True)
        _configure_sqlite(engine)
        return engine
    # Managed Postgres (e.g. Supabase): pre-ping and recycle so a connection the
    # provider dropped while idle is replaced rather than handed out dead, and
    # turn off asyncpg's prepared-statement cache so the app also works through a
    # transaction-mode pooler (pgbouncer), where cached statements don't survive
    # across pooled connections. (Prefer Supabase's session pooler / direct URL.)
    connect_args = {"statement_cache_size": 0} if "asyncpg" in database_url else {}
    return create_async_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args=connect_args,
    )


def _configure_sqlite(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragma(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")  # concurrent readers during writes
        cursor.execute("PRAGMA synchronous=NORMAL")  # safe + fast under WAL
        cursor.execute("PRAGMA busy_timeout=5000")  # ride out brief lock contention
        cursor.close()


class Database:
    """Owns the engine and hands out sessions for the application's lifetime."""

    def __init__(self, database_url: str) -> None:
        self.url = database_url
        self.engine = create_engine(database_url)
        self._session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_all(self) -> None:
        # Import the models module so every table is registered on Base.metadata.
        from driftwatch import models  # noqa: F401

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def upgrade(self) -> None:
        """Bring the schema to the latest Alembic revision, creating it on a fresh
        database and migrating an existing one in place. Alembic's API is
        synchronous, so it runs in a worker thread off the event loop."""
        await to_thread.run_sync(_run_migrations, self.url)

    async def require_migration_head(self) -> None:
        """Fail unless the database is already versioned at this release's head.

        Deployments that run migrations in a separate release phase use this
        check at application startup. It deliberately performs no schema writes.
        """
        await to_thread.run_sync(_require_migration_head, self.url)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            yield session

    async def ping(self) -> None:
        """Verify that the database can execute a query.

        Readiness uses a real round-trip rather than merely checking that an
        engine object exists; a dead pool, revoked credentials, or unavailable
        server must make the deployment unready.
        """
        async with self._session_factory() as session:
            await session.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self.engine.dispose()


def sync_database_url(url: str) -> str:
    """Map an async driver URL to its synchronous peer, which Alembic needs."""
    return url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg")


def _run_migrations(database_url: str) -> None:
    """Bring ``database_url`` to head with Alembic (synchronous).

    A genuinely empty database is built by the upgrade, and an already-tracked
    one is migrated forward. A non-empty database without Alembic provenance is
    rejected: stamping it would skip data migrations and database-only controls
    that cannot be inferred from ORM metadata.
    """
    from alembic import command

    config = _alembic_config(database_url)
    if _has_unversioned_schema(sync_database_url(database_url)):
        raise RuntimeError(
            "Refusing to migrate a non-empty database without Alembic provenance. "
            "Restore a versioned backup or use an explicit, reviewed migration from "
            "the database's known application version; never stamp it directly to head."
        )
    command.upgrade(config, "head")


def _alembic_config(database_url: str) -> Config:
    alembic_ini, migrations_dir = _alembic_paths()
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(migrations_dir))
    config.set_main_option("sqlalchemy.url", sync_database_url(database_url))
    return config


def _has_unversioned_schema(sync_url: str) -> bool:
    from sqlalchemy import create_engine as create_sync_engine
    from sqlalchemy import inspect

    engine = create_sync_engine(sync_url)
    try:
        tables = set(inspect(engine).get_table_names())
        return bool(tables) and "alembic_version" not in tables
    finally:
        engine.dispose()


def _require_migration_head(database_url: str) -> None:
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine as create_sync_engine

    config = _alembic_config(database_url)
    expected = set(ScriptDirectory.from_config(config).get_heads())
    engine = create_sync_engine(sync_database_url(database_url))
    try:
        with engine.connect() as connection:
            current = set(MigrationContext.configure(connection).get_current_heads())
    finally:
        engine.dispose()
    if current != expected:
        current_label = ", ".join(sorted(current)) or "unversioned/empty"
        expected_label = ", ".join(sorted(expected)) or "no migration head"
        raise RuntimeError(
            "Database schema is not at the required Alembic head "
            f"(current: {current_label}; required: {expected_label}). "
            "Run `driftwatch migrate` in the release phase before starting the service."
        )


def sqlite_file_path(database_url: str) -> Path | None:
    """The on-disk path of a SQLite ``database_url``, or ``None`` for other backends."""
    if not database_url.startswith("sqlite"):
        return None
    return Path(database_url.split(":///", 1)[-1])


def snapshot_sqlite(source: Path, dest: Path) -> None:
    """Copy ``source`` to ``dest`` as a consistent SQLite snapshot.

    Uses the online-backup API rather than a raw file copy so the snapshot
    includes committed pages still living in the WAL — which a plain copy of the
    main database file would silently omit.
    """
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(dest)) as out:
        src.backup(out)


def overwrite_sqlite(source: Path, dest: Path) -> None:
    """Replace the contents of the live database ``dest`` with ``source``.

    The backup API writes through SQLite's own locking, so it is safe while the
    engine still holds connections to ``dest``; callers dispose the engine pool
    afterwards to drop now-stale cached pages.
    """
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(dest, timeout=10)) as out:
        out.execute("PRAGMA busy_timeout=10000")
        src.backup(out)


def validate_sqlite_snapshot(path: Path) -> None:
    """Raise :class:`ValueError` unless ``path`` is an intact SQLite database that
    carries this application's core tables."""
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("the file failed a SQLite integrity check")
            present = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
    except sqlite3.DatabaseError as exc:
        raise ValueError("the file is not a valid SQLite database") from exc
    missing = _REQUIRED_TABLES - present
    if missing:
        raise ValueError(f"the backup is missing expected tables: {', '.join(sorted(missing))}")
