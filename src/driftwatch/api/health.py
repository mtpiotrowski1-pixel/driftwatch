"""Liveness endpoint for external monitoring."""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from driftwatch.api.deps import DatabaseDep, SettingsDep
from driftwatch.config import Settings
from driftwatch.db import sqlite_file_path
from driftwatch.monitoring.capture import CaptureError
from driftwatch.monitoring.remote_capture import RemotePageCapturer
from driftwatch.scheduler import MonitorScheduler

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


def _storage_metrics(settings: Settings) -> dict[str, int | None]:
    """Database and disk footprint on the SQLite backend; all null on Postgres,
    where storage is the provider's concern."""
    db_path = sqlite_file_path(settings.database_url)
    if db_path is None:
        return {"db_bytes": None, "wal_bytes": None, "disk_free_bytes": None}
    wal = db_path.with_name(db_path.name + "-wal")
    try:
        disk_free: int | None = shutil.disk_usage(settings.data_dir).free
    except OSError:
        disk_free = None
    return {
        "db_bytes": db_path.stat().st_size if db_path.exists() else None,
        "wal_bytes": wal.stat().st_size if wal.exists() else 0,
        "disk_free_bytes": disk_free,
    }


@router.get("/livez")
async def livez() -> dict[str, str]:
    """Process liveness; dependency health belongs to readiness."""
    return {"status": "ok"}


@router.get("/healthz")
@router.get("/readyz")
async def healthz(
    request: Request,
    settings: SettingsDep,
    database: DatabaseDep,
) -> JSONResponse:
    scheduler = getattr(request.app.state, "scheduler", None)
    running = bool(scheduler and scheduler.running)
    scheduler_stale = _scheduler_is_stale(scheduler, settings, datetime.now(UTC))
    try:
        await database.ping()
        database_ok = True
    except Exception:
        database_ok = False
        logger.exception("database readiness check failed")
    scheduler_ok = not bool(scheduler and scheduler.expected and (not running or scheduler_stale))
    capture_status = await _capture_status(request)
    routing_ready = database_ok and scheduler_ok
    degraded = not routing_ready or capture_status == "unavailable"
    payload = {
        "status": "degraded" if degraded else "ok",
        "routing_ready": routing_ready,
        "dependencies": {
            "database": "ready" if database_ok else "unavailable",
            "scheduler": _scheduler_status(scheduler, running, scheduler_stale),
            "capture": capture_status,
        },
    }
    # Capture is an asynchronous product capability. Removing the API/SPA from
    # routing when its isolated worker is down would also remove billing and the
    # Operations surface needed to diagnose it. Database and the expected
    # scheduler remain hard routing dependencies.
    code = status.HTTP_200_OK if routing_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(payload, status_code=code)


async def _capture_status(request: Request) -> str:
    capturer = getattr(request.app.state, "page_capturer", None)
    if not isinstance(capturer, RemotePageCapturer):
        return "not_probed"
    try:
        await capturer.probe()
    except CaptureError:
        logger.warning("capture worker readiness check failed", exc_info=True)
        return "unavailable"
    return "ready"


def _scheduler_status(
    scheduler: MonitorScheduler | None,
    running: bool,
    stale: bool,
) -> str:
    if scheduler is None or not scheduler.expected:
        return "disabled"
    if not running:
        return "stopped"
    return "stale" if stale else "ready"


def _scheduler_is_stale(
    scheduler: MonitorScheduler | None,
    settings: Settings,
    now: datetime,
) -> bool:
    if scheduler is None or not scheduler.expected:
        return False
    threshold = timedelta(seconds=max(settings.scheduler_tick_seconds * 3, 90))
    reference = scheduler.last_tick_at or scheduler.started_at
    if reference is None:
        return True
    return now - reference > threshold
