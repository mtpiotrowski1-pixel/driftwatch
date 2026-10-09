"""Process entry point and release-time database command."""

from __future__ import annotations

import argparse
import asyncio

from driftwatch.app import run as serve
from driftwatch.config import Settings, get_settings
from driftwatch.db import Database
from driftwatch.logging_setup import configure_logging


def run() -> None:  # pragma: no cover - exercised through the installed command
    parser = argparse.ArgumentParser(prog="driftwatch")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("serve", "migrate"),
        default="serve",
        help="serve the application or migrate its database to the current schema",
    )
    command = parser.parse_args().command
    settings = get_settings()
    if command == "migrate":
        configure_logging(settings)
        asyncio.run(migrate(settings))
        return
    serve()


async def migrate(settings: Settings) -> None:
    database = Database(settings.database_url)
    try:
        await database.upgrade()
    finally:
        await database.dispose()
