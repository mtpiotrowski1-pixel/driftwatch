"""Request and scheduler draining around destructive maintenance."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from types import MethodType

import httpx
from fastapi import FastAPI

from driftwatch.api.error_contract import RequestIdMiddleware
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.maintenance import MaintenanceGate, MaintenanceMode
from driftwatch.runner import SiteRunner
from driftwatch.scheduler import MonitorScheduler
from tests.conftest import ScriptedCapturer


async def test_maintenance_rejects_new_requests_and_drains_existing_ones() -> None:
    mode = MaintenanceMode()
    assert await mode.enter_request()  # restore request itself
    assert await mode.enter_request()  # another request already in flight

    exclusive_entered = asyncio.Event()
    release = asyncio.Event()

    async def maintain() -> None:
        async with mode.exclusive():
            exclusive_entered.set()
            await release.wait()

    task = asyncio.create_task(maintain())
    await asyncio.sleep(0)
    assert mode.enabled
    assert not exclusive_entered.is_set()
    assert await mode.enter_request() is False

    await mode.leave_request()
    await asyncio.wait_for(exclusive_entered.wait(), timeout=1)
    release.set()
    await task
    assert not mode.enabled

    await mode.leave_request()
    assert mode.active_requests == 0
    assert await mode.enter_request()
    await mode.leave_request()


async def test_cancelled_drain_does_not_leave_maintenance_enabled() -> None:
    mode = MaintenanceMode()
    assert await mode.enter_request()

    async def wait_for_drain() -> None:
        async with mode.exclusive(includes_caller=False):
            raise AssertionError("the active request should keep this waiting")

    task = asyncio.create_task(wait_for_drain())
    await asyncio.sleep(0)
    assert mode.enabled
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert not mode.enabled
    await mode.leave_request()


async def test_http_gate_keeps_liveness_open_and_returns_correlated_503() -> None:
    mode = MaintenanceMode()
    app = FastAPI()
    app.add_middleware(MaintenanceGate, mode=mode)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/livez")
    async def livez() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        return {"status": "ok"}

    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        mode.exclusive(includes_caller=False),
    ):
        live = await client.get("/livez", headers={"X-Request-ID": "live-1"})
        ready = await client.get("/readyz", headers={"X-Request-ID": "ready-1"})

    assert live.status_code == 200
    assert ready.status_code == 503
    assert ready.headers["Retry-After"] == "30"
    assert ready.json() == {
        "detail": "Service temporarily unavailable during maintenance",
        "error_code": "maintenance_mode",
        "request_id": "ready-1",
    }


async def test_scheduler_pause_waits_for_active_tick_and_blocks_new_tick(
    database: Database, settings: Settings
) -> None:
    scheduler = MonitorScheduler(
        database,
        SiteRunner(database, ScriptedCapturer(), settings),
        settings,
    )
    tick_entered = asyncio.Event()
    finish_tick = asyncio.Event()

    async def slow_tick(_self: MonitorScheduler) -> None:
        tick_entered.set()
        await finish_tick.wait()

    scheduler._run_tick = MethodType(slow_tick, scheduler)  # type: ignore[method-assign]
    active_tick = asyncio.create_task(scheduler.tick())
    await asyncio.wait_for(tick_entered.wait(), timeout=1)

    maintenance_entered = asyncio.Event()
    release_maintenance = asyncio.Event()

    async def maintain() -> None:
        async with scheduler.paused_for_maintenance():
            maintenance_entered.set()
            await release_maintenance.wait()

    maintenance = asyncio.create_task(maintain())
    await asyncio.sleep(0)
    assert not maintenance_entered.is_set()

    finish_tick.set()
    await active_tick
    await asyncio.wait_for(maintenance_entered.wait(), timeout=1)

    blocked_tick = asyncio.create_task(scheduler.tick())
    await asyncio.wait_for(blocked_tick, timeout=1)
    assert tick_entered.is_set()

    release_maintenance.set()
    await maintenance
