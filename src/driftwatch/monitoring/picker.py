"""Interactive visual selector picker (headed browser on the backend host).

A non-technical user clicks element(s) to choose what to monitor and can record
click/type steps. The overlay runs in a *visible* browser launched on the
machine running the backend — it needs a display, so it is unavailable on a
headless server — driven by Playwright over CDP so it works with any installed
Edge/Chrome version. The
overlay pushes results to :meth:`PickerSession._emit` via a Playwright binding —
no in-page polling — and the authoritative selector/step state lives here.

Importing this module never starts a browser: Playwright and ``overlay.js`` are
loaded lazily inside the session.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from driftwatch.exceptions import ConflictError, InvalidRequest, NotFoundError
from driftwatch.monitoring.browser import (
    BrowserChannel,
    BrowserUnavailable,
    resolve_launch_plan,
)
from driftwatch.monitoring.network_guard import (
    BrowserNetworkBlocked,
    BrowserNetworkGuard,
    hardened_context_options,
)
from driftwatch.security.urls import resolve_public_url, validate_public_url

logger = logging.getLogger(__name__)

_OVERLAY_PATH = Path(__file__).with_name("overlay.js")


async def _resolver_pin(url: str) -> str | None:
    """A Chromium ``--host-resolver-rules`` arg pinning the host to its validated
    IP, so the headed browser connects to the exact address the SSRF check
    approved — closing the resolve-vs-connect DNS-rebind window, as the capturer
    does. ``None`` for an IP-literal host."""
    host = urlsplit(url).hostname
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
        return None  # already a literal IP — nothing to pin
    except ValueError:
        pass
    _url, ips = await resolve_public_url(url)
    return f"--host-resolver-rules=MAP {host} {ips[0]}" if ips else None


class PickerMode(StrEnum):
    SELECT = "select"
    RECORD = "record"


class PickerState(StrEnum):
    STARTING = "starting"
    WAITING = "waiting"
    SAVED = "saved"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    ERROR = "error"


_TERMINAL = {PickerState.SAVED, PickerState.CANCELLED, PickerState.TIMED_OUT, PickerState.ERROR}


class PickerUnavailable(RuntimeError):
    """The visual picker cannot run here (disabled, no display, or no browser)."""


@dataclass(frozen=True, slots=True)
class PickerResult:
    selectors: list[str]
    steps: list[dict[str, Any]]

    @property
    def css_selector(self) -> str:
        return ", ".join(self.selectors)


@dataclass(slots=True)
class PickerStatus:
    session_id: str
    state: PickerState
    mode: PickerMode
    selector_count: int
    step_count: int
    channel: str | None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class PickerCapabilities:
    available: bool
    reason: str | None = None


def normalize_step(raw: dict[str, Any]) -> dict[str, Any]:
    """Map an overlay step without returning text typed into the page.

    A recorded fill carries only its selector. The user supplies the value in
    Driftwatch's password-style editor, where it can go directly to the vault.
    """
    action = "fill" if raw.get("type") == "type" else "click"
    return {
        "action": action,
        "selector": raw.get("selector"),
        "timeout_ms": 10_000,
    }


class PickerService(Protocol):
    async def start(self, *, url: str, mode: PickerMode, owner_user_id: int) -> PickerStatus: ...
    async def status(self, session_id: str, *, requester_id: int) -> PickerStatus: ...
    async def result(self, session_id: str, *, requester_id: int) -> PickerResult: ...
    async def cancel(self, session_id: str, *, requester_id: int) -> None: ...
    async def capabilities(self) -> PickerCapabilities: ...
    async def shutdown(self) -> None: ...


class PickerSession:
    def __init__(
        self,
        *,
        session_id: str,
        url: str,
        mode: PickerMode,
        channel: BrowserChannel,
        user_agent: str,
        session_timeout: float,
        idle_timeout: float,
        owner_user_id: int,
    ) -> None:
        self.session_id = session_id
        self.owner_user_id = owner_user_id
        self._url = url
        self._mode = mode
        self._channel = channel
        self._user_agent = user_agent
        self._session_timeout = session_timeout
        self._idle_timeout = idle_timeout

        self._state = PickerState.STARTING
        self._selectors: list[str] = []
        self._steps: list[dict[str, Any]] = []
        self._channel_name: str | None = None
        self._detail: str | None = None

        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._network_guard: BrowserNetworkGuard | None = None
        self._overlay_js = ""
        self._watchdog: asyncio.Task[None] | None = None
        self._reinjects: set[asyncio.Task[None]] = set()
        self._closed = False
        self._started_at = 0.0
        self._last_touch = 0.0

    async def start(self) -> None:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright

        self._overlay_js = _OVERLAY_PATH.read_text(encoding="utf-8")
        loop = asyncio.get_running_loop()
        self._started_at = loop.time()
        self._last_touch = self._started_at
        try:
            resolver_arg = await _resolver_pin(self._url)
            self._pw = await async_playwright().start()
            plan = await resolve_launch_plan(self._pw, forced=self._channel, headless=False)
            self._channel_name = plan.channel.value
            launch_kwargs = dict(plan.launch_kwargs)
            if resolver_arg:
                launch_kwargs["args"] = [*launch_kwargs.get("args", []), resolver_arg]
            self._browser = await self._pw.chromium.launch(headless=False, **launch_kwargs)
            self._context = await self._browser.new_context(
                **hardened_context_options(user_agent=self._user_agent)
            )
            self._network_guard = BrowserNetworkGuard()
            await self._network_guard.install(self._context)
            await self._context.expose_binding("__driftwatch_emit", self._emit)
            await self._context.add_init_script(
                f"window.__driftwatch_init_mode = {json.dumps(self._mode.value)};"
            )
            self._page = await self._context.new_page()
            self._network_guard.attach_page(self._page)
            self._network_guard.reject_future_pages(self._context)
            self._page.on("load", lambda *_: self._schedule_reinject())
            self._page.on("close", lambda *_: self._on_disconnect())
            self._browser.on("disconnected", lambda *_: self._on_disconnect())
            await self._page.goto(self._url, wait_until="domcontentloaded")
            if not await self._network_allowed():
                await self.aclose()
                return
            await self._inject_overlay()
            if self._state in _TERMINAL:  # the navigation guard rejected the page
                return
        except BrowserUnavailable as exc:
            await self.aclose()
            raise PickerUnavailable(str(exc)) from exc
        except PlaywrightError as exc:
            if not await self._network_allowed():
                await self.aclose()
                return
            await self.aclose()
            raise PickerUnavailable(
                "Could not open a visible browser window on the server. The visual picker "
                "needs a desktop session on the machine running Driftwatch. Enter the "
                f"selector manually instead. ({exc})"
            ) from exc

        self._state = PickerState.WAITING
        self._watchdog = asyncio.create_task(self._watch())

    def status(self) -> PickerStatus:
        return PickerStatus(
            session_id=self.session_id,
            state=self._state,
            mode=self._mode,
            selector_count=len(self._selectors),
            step_count=len(self._steps),
            channel=self._channel_name,
            detail=self._detail,
        )

    def result(self) -> PickerResult:
        return PickerResult(selectors=list(self._selectors), steps=list(self._steps))

    async def cancel(self) -> None:
        if self._state not in _TERMINAL:
            self._state = PickerState.CANCELLED
        await self.aclose()

    async def _emit(self, _source: dict[str, Any], payload: dict[str, Any]) -> dict[str, int]:
        self._last_touch = asyncio.get_running_loop().time()
        kind = payload.get("type")
        if kind == "select":
            self._selectors = [str(s) for s in payload.get("selectors") or []]
        elif kind == "step":
            self._steps.append(normalize_step(payload.get("step") or {}))
        elif kind == "clear":
            self._steps.clear()
        elif kind == "save":
            self._state = PickerState.SAVED
        elif kind == "cancel":
            self._state = PickerState.CANCELLED
        return {"stepCount": len(self._steps), "selectorCount": len(self._selectors)}

    def _schedule_reinject(self) -> None:
        if self._state is PickerState.WAITING or self._state is PickerState.STARTING:
            task = asyncio.create_task(self._inject_overlay())
            self._reinjects.add(task)
            task.add_done_callback(self._reinjects.discard)

    async def _inject_overlay(self) -> None:
        if not await self._network_allowed():
            await self.aclose()
            return
        if not await self._is_public(self._page.url):
            self._detail = "Navigation reached a non-public address; the session was stopped."
            self._state = PickerState.ERROR
            await self.aclose()
            return
        try:
            await self._page.evaluate(self._overlay_js)
        except Exception:  # navigation in flight; the next load event retries
            logger.debug("overlay injection deferred", exc_info=True)

    @staticmethod
    async def _is_public(url: str) -> bool:
        """Guard the headed browser against redirect/DNS-rebind SSRF: the picker
        re-validates the URL it actually landed on, mirroring the capture path."""
        try:
            await validate_public_url(url)
        except InvalidRequest:
            return False
        return True

    async def _network_allowed(self) -> bool:
        if self._network_guard is None:
            return True
        try:
            await self._network_guard.checkpoint()
        except BrowserNetworkBlocked as exc:
            self._detail = str(exc)
            self._state = PickerState.ERROR
            return False
        return True

    def _on_disconnect(self) -> None:
        if self._state not in _TERMINAL:
            self._state = PickerState.CANCELLED

    async def _watch(self) -> None:
        loop = asyncio.get_running_loop()
        while self._state is PickerState.WAITING:
            await asyncio.sleep(3)
            if not await self._network_allowed():
                break
            now = loop.time()
            if now - self._started_at >= self._session_timeout or (
                now - self._last_touch >= self._idle_timeout
            ):
                self._state = PickerState.TIMED_OUT
                break
        if self._state in _TERMINAL:
            await self.aclose()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._cancel_pending_tasks()
        if self._network_guard is not None:
            await self._network_guard.aclose()
        for closer in (self._closer(self._context), self._closer(self._browser), self._stopper()):
            await closer

    def _cancel_pending_tasks(self) -> None:
        """Cancel reinjection and watchdog work, but never the calling task —
        ``aclose`` may be invoked from within the watchdog itself."""
        current = asyncio.current_task()
        pending = {*self._reinjects, self._watchdog}
        for task in pending:
            if task is not None and task is not current and not task.done():
                task.cancel()

    @staticmethod
    async def _closer(obj: Any) -> None:
        if obj is not None:
            try:
                await obj.close()
            except Exception:
                logger.debug("error closing picker resource", exc_info=True)

    async def _stopper(self) -> None:
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                logger.debug("error stopping playwright", exc_info=True)


class PickerManager:
    """Process-wide owner of at most one interactive picker session."""

    def __init__(
        self,
        *,
        enabled: bool,
        channel: BrowserChannel,
        user_agent: str,
        session_timeout: float,
        idle_timeout: float,
    ) -> None:
        self._enabled = enabled
        self._channel = channel
        self._user_agent = user_agent
        self._session_timeout = session_timeout
        self._idle_timeout = idle_timeout
        self._lock = asyncio.Lock()
        self._session: PickerSession | None = None

    async def start(self, *, url: str, mode: PickerMode, owner_user_id: int) -> PickerStatus:
        if not self._enabled:
            raise PickerUnavailable("The visual picker is disabled on this deployment.")
        async with self._lock:
            if self._session is not None and self._session._state is PickerState.WAITING:
                raise ConflictError("Another visual picker session is already open.")
            if self._session is not None:
                await self._session.aclose()
            session = PickerSession(
                session_id=uuid.uuid4().hex,
                url=url,
                mode=mode,
                channel=self._channel,
                user_agent=self._user_agent,
                session_timeout=self._session_timeout,
                idle_timeout=self._idle_timeout,
                owner_user_id=owner_user_id,
            )
            await session.start()
            self._session = session
            return session.status()

    async def status(self, session_id: str, *, requester_id: int) -> PickerStatus:
        return self._require(session_id, requester_id).status()

    async def result(self, session_id: str, *, requester_id: int) -> PickerResult:
        session = self._require(session_id, requester_id)
        if session._state is not PickerState.SAVED:
            raise ConflictError("The picker session has no saved result.")
        return session.result()

    async def cancel(self, session_id: str, *, requester_id: int) -> None:
        session = self._session
        if (
            session is not None
            and session.session_id == session_id
            and session.owner_user_id == requester_id
        ):
            await session.cancel()

    async def capabilities(self) -> PickerCapabilities:
        if not self._enabled:
            return PickerCapabilities(available=False, reason="The visual picker is disabled.")
        return PickerCapabilities(available=True)

    async def shutdown(self) -> None:
        if self._session is not None:
            await self._session.aclose()

    def _require(self, session_id: str, requester_id: int) -> PickerSession:
        # A 404 (not 403) on a mismatch avoids confirming another user's session.
        session = self._session
        if session is None or session.session_id != session_id:
            raise NotFoundError(f"picker session {session_id} not found")
        if session.owner_user_id != requester_id:
            raise NotFoundError(f"picker session {session_id} not found")
        return session
