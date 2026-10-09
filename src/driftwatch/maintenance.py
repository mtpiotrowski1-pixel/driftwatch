"""Process-local request draining for destructive maintenance operations.

SQLite restore is supported only for a single application process. This
coordinator prevents new database-backed HTTP requests from entering while the
restore request waits for all requests that were already in flight to finish.
The scheduler has its own drain lock because it does not pass through HTTP.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from driftwatch.api.error_contract import error_response


class MaintenanceAlreadyActive(RuntimeError):
    """Raised when a second destructive operation races an active one."""


class MaintenanceMode:
    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._enabled = False
        self._active_requests = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def active_requests(self) -> int:
        return self._active_requests

    async def enter_request(self) -> bool:
        """Register a normal request, or reject it once maintenance has begun."""
        async with self._condition:
            if self._enabled:
                return False
            self._active_requests += 1
            return True

    async def leave_request(self) -> None:
        async with self._condition:
            if self._active_requests <= 0:
                raise RuntimeError("maintenance request accounting underflow")
            self._active_requests -= 1
            self._condition.notify_all()

    @asynccontextmanager
    async def exclusive(self, *, includes_caller: bool = True) -> AsyncIterator[None]:
        """Reject new requests and wait until pre-existing work has drained.

        An HTTP handler invoking this method has already been registered by the
        maintenance middleware, so one active request (the caller) is expected.
        Non-HTTP maintenance callers set ``includes_caller=False``.
        """
        remaining = 1 if includes_caller else 0
        claimed = False
        try:
            async with self._condition:
                if self._enabled:
                    raise MaintenanceAlreadyActive("another maintenance operation is active")
                self._enabled = True
                claimed = True
                await self._condition.wait_for(lambda: self._active_requests <= remaining)
            yield
        finally:
            if claimed:
                async with self._condition:
                    self._enabled = False
                    self._condition.notify_all()


class MaintenanceGate:
    """Drain-aware ASGI gate for database-backed HTTP traffic.

    Liveness is deliberately exempt: the process remains alive during restore,
    while readiness and all product routes return a correlated 503.
    """

    def __init__(self, app: ASGIApp, mode: MaintenanceMode) -> None:
        self._app = app
        self._mode = mode

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == "/livez":
            await self._app(scope, receive, send)
            return

        entered = await self._mode.enter_request()
        if not entered:
            request = Request(scope, receive)
            response = error_response(
                request,
                status_code=503,
                detail="Service temporarily unavailable during maintenance",
                error_code="maintenance_mode",
                headers={"Retry-After": "30"},
            )
            await response(scope, receive, send)
            return
        try:
            await self._app(scope, receive, send)
        finally:
            await self._mode.leave_request()
