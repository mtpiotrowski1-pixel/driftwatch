"""Release-time command behavior."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect

from driftwatch.cli import migrate
from driftwatch.config import Settings


async def test_migrate_command_builds_a_versioned_schema(tmp_path: Path) -> None:
    database = tmp_path / "release.db"
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite+aiosqlite:///{database}",
        run_migrations=True,
    )

    await migrate(settings)

    engine = create_engine(f"sqlite:///{database}")
    try:
        inspector = inspect(engine)
        assert inspector.has_table("organizations")
        assert inspector.has_table("alembic_version")
    finally:
        engine.dispose()
