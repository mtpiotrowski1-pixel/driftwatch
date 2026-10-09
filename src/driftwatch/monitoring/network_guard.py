"""Fail-closed network policy for Playwright browser contexts.

The monitored document is untrusted. Validating only its initial URL leaves
redirects, subresources, WebSockets, popups, and downloads able to target the
host network. :class:`BrowserNetworkGuard` is installed on the context before a
page exists and applies the same public-address policy to every routed request.

Playwright routing is an application-layer control, not an egress firewall. A
production deployment should still run capture workers in an isolated network
namespace whose firewall denies private, link-local, and metadata ranges.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from driftwatch.exceptions import InvalidRequest
from driftwatch.security.urls import validate_public_url

logger = logging.getLogger(__name__)

UrlValidator = Callable[[str], Awaitable[str]]


class BrowserNetworkBlocked(RuntimeError):
    """The browser attempted an operation forbidden by the capture policy."""


@dataclass(frozen=True, slots=True)
class NetworkViolation:
    operation: str
    detail: str


def hardened_context_options(*, user_agent: str) -> dict[str, Any]:
    """Options shared by headed and headless untrusted browser contexts."""
    return {
        "accept_downloads": False,
        "service_workers": "block",
        "user_agent": user_agent,
    }


class BrowserNetworkGuard:
    """Apply and record a fail-closed network policy for one browser context.

    A blocked auxiliary request is not silently ignored. The first violation is
    retained and :meth:`checkpoint` fails the entire capture/session, preventing
    partially rendered content from being accepted as a valid observation.
    """

    def __init__(self, *, validate_url: UrlValidator = validate_public_url) -> None:
        self._validate_url = validate_url
        self._violation: NetworkViolation | None = None
        self._active_handlers = 0
        self._handlers_idle = asyncio.Event()
        self._handlers_idle.set()
        self._background_tasks: set[asyncio.Task[Any]] = set()

    @property
    def violation(self) -> NetworkViolation | None:
        return self._violation

    async def install(self, context: Any) -> None:
        """Install guards before the context creates its first page."""
        await context.route("**/*", self._handle_request)
        await context.route_web_socket("**/*", self._handle_websocket)

    def attach_page(self, page: Any) -> None:
        """Cancel downloads initiated by the primary page."""
        page.on("download", self._handle_download)

    def reject_future_pages(self, context: Any) -> None:
        """Close any popup/new page created after the primary page."""
        context.on("page", self._handle_popup)

    async def checkpoint(self) -> None:
        """Wait for current policy decisions and raise on the first violation."""
        await self._handlers_idle.wait()
        if self._violation is not None:
            raise BrowserNetworkBlocked(self._violation.detail)

    async def aclose(self) -> None:
        """Drain popup/download cancellation tasks and consume their errors."""
        if self._background_tasks:
            await asyncio.gather(*tuple(self._background_tasks), return_exceptions=True)

    async def _handle_request(self, route: Any) -> None:
        self._handler_started()
        try:
            try:
                await self._validate_http_url(str(route.request.url))
            except InvalidRequest:
                self._record(
                    "request", "Browser request targeted a non-public or unsupported address."
                )
                await route.abort("blockedbyclient")
                return
            except Exception as exc:
                # Resolver/client exceptions may embed the target URL. This code
                # runs in the isolated worker, whose logs intentionally contain
                # neither customer targets nor interaction values.
                logger.warning(
                    "browser request URL validation failed: type=%s",
                    type(exc).__name__,
                )
                self._record("request", "Browser request could not be safely validated.")
                await route.abort("blockedbyclient")
                return
            await route.continue_()
        finally:
            self._handler_finished()

    async def _handle_websocket(self, websocket: Any) -> None:
        self._handler_started()
        try:
            try:
                await self._validate_websocket_url(str(websocket.url))
            except InvalidRequest:
                self._record(
                    "websocket",
                    "Browser WebSocket targeted a non-public or unsupported address.",
                )
                await websocket.close(code=1008, reason="Blocked by browser network policy")
                return
            except Exception as exc:
                logger.warning(
                    "browser WebSocket URL validation failed: type=%s",
                    type(exc).__name__,
                )
                self._record("websocket", "Browser WebSocket could not be safely validated.")
                await websocket.close(code=1008, reason="Blocked by browser network policy")
                return
            await websocket.connect_to_server()
        finally:
            self._handler_finished()

    def _handle_download(self, download: Any) -> None:
        self._record("download", "Browser-initiated downloads are disabled during capture.")
        self._spawn(download.cancel())

    def _handle_popup(self, page: Any) -> None:
        self._record("popup", "Browser-initiated popups are disabled during capture.")
        self._spawn(page.close())

    async def _validate_http_url(self, raw: str) -> None:
        if urlsplit(raw).scheme.lower() not in {"http", "https"}:
            raise InvalidRequest("browser request scheme is not allowed")
        await self._validate_url(raw)

    async def _validate_websocket_url(self, raw: str) -> None:
        parsed = urlsplit(raw)
        scheme = parsed.scheme.lower()
        if scheme not in {"ws", "wss"}:
            raise InvalidRequest("browser WebSocket scheme is not allowed")
        validation_scheme = "https" if scheme == "wss" else "http"
        await self._validate_url(urlunsplit(parsed._replace(scheme=validation_scheme)))

    def _record(self, operation: str, detail: str) -> None:
        if self._violation is None:
            self._violation = NetworkViolation(operation=operation, detail=detail)

    def _handler_started(self) -> None:
        self._active_handlers += 1
        self._handlers_idle.clear()

    def _handler_finished(self) -> None:
        self._active_handlers -= 1
        if self._active_handlers == 0:
            self._handlers_idle.set()

    def _spawn(self, awaitable: Coroutine[Any, Any, Any]) -> None:
        task: asyncio.Task[Any] = asyncio.create_task(awaitable)
        self._background_tasks.add(task)
        task.add_done_callback(self._finish_background_task)

    def _finish_background_task(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.discard(task)
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.debug("browser policy cleanup failed", exc_info=True)
