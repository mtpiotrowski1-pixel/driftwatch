"""Fetch the rendered HTML of a page.

The pipeline depends on the :class:`PageCapturer` protocol; the Playwright
implementation is injected at runtime and lazy-imports the library so importing
this module never requires a browser download. Before reading the DOM the
capturer can replay a short script of interactions (click, fill, wait) to reach
content behind a cookie wall, tab, or "load more" button.

Some failures are not transient and must not be retried or mistaken for "no
change": a configured selector that no longer matches, or a bot-protection
interstitial. Those raise dedicated errors that the runner turns into an
operational alert instead of a snapshot.
"""

from __future__ import annotations

import asyncio
import ipaddress
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit

from driftwatch.enums import AlertCode
from driftwatch.exceptions import InvalidRequest
from driftwatch.monitoring.browser import (
    BrowserChannel,
    BrowserUnavailable,
    LaunchPlan,
    resolve_launch_plan,
)
from driftwatch.monitoring.network_guard import (
    BrowserNetworkBlocked,
    BrowserNetworkGuard,
    hardened_context_options,
)
from driftwatch.security.origins import http_origin
from driftwatch.security.urls import UnresolvableHost, resolve_public_url, validate_public_url

# Markers that strongly indicate a bot-protection or block interstitial rather
# than the real page. Kept conservative to avoid false positives on real content.
_BLOCK_MARKERS: tuple[str, ...] = (
    "verify you are human",
    "checking your browser before",
    "are you a robot",
    "enable javascript and cookies to continue",
    "ddos protection by",
    "request unsuccessful. incapsula",
)

# A monitored page returning a huge body would otherwise be parsed, diffed against
# the stored snapshot, and persisted at full size — a 2-3x memory amplification per
# check. Bound the captured content so one giant page can't OOM the instance.
_MAX_CONTENT_CHARS = 4_000_000


def _cap(content: str) -> str:
    if len(content) > _MAX_CONTENT_CHARS:
        raise CaptureContentTooLarge("monitored content exceeds the capture size limit")
    return content


class CaptureError(Exception):
    """A page could not be captured. Transient unless a subclass says otherwise."""

    code: AlertCode = AlertCode.CAPTURE_FAILED
    transient: bool = True


class CaptureSelectorMissing(CaptureError):
    """The configured CSS selector matched nothing on the page."""

    code = AlertCode.SELECTOR_MISSING
    transient = False


class CaptureBlocked(CaptureError):
    """The response looked like a bot-protection or block interstitial."""

    code = AlertCode.BLOCKED
    transient = False


class CaptureHttpError(CaptureError):
    """An HTTP error page is a failed capture, never a new baseline."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"monitored page returned HTTP {status_code}")
        self.status_code = status_code
        self.transient = status_code >= 500 or status_code in {408, 429}


class CaptureContentTooLarge(CaptureError):
    """A partial observation must not be accepted as a complete snapshot."""

    transient = False


@dataclass(frozen=True, slots=True)
class CapturedPage:
    html: str
    base_url: str


@dataclass(frozen=True, slots=True)
class CaptureTiming:
    timeout_seconds: float
    settle_ms: int


@runtime_checkable
class SupportsCaptureTiming(Protocol):
    def apply_timing(self, *, timeout_seconds: float, settle_ms: int) -> None: ...


@dataclass(frozen=True, slots=True)
class InteractionStep:
    action: str  # "click" | "fill" | "wait_for" | "wait"
    selector: str | None = None
    value: str | None = field(default=None, repr=False)
    allowed_origin: str | None = None
    timeout_ms: int = 10_000

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> InteractionStep:
        return cls(
            action=str(raw.get("action", "")).strip(),
            selector=raw.get("selector"),
            value=raw.get("value"),
            allowed_origin=raw.get("allowed_origin"),
            timeout_ms=int(raw.get("timeout_ms", 10_000)),
        )


class PageCapturer(Protocol):
    async def capture(
        self,
        *,
        url: str,
        css_selector: str | None = None,
        interaction_steps: list[dict[str, Any]] | None = None,
        timing: CaptureTiming | None = None,
    ) -> str | CapturedPage: ...


class PlaywrightCapturer:
    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        settle_ms: int = 750,
        user_agent: str = "DriftwatchBot/1.0",
        channel: BrowserChannel = BrowserChannel.AUTO,
        pin_dns: bool = True,
        launch_timeout_seconds: float = 30.0,
        max_concurrent: int = 4,
        browser_environment: dict[str, str] | None = None,
    ) -> None:
        self._timeout_ms = int(timeout_seconds * 1000)
        self._settle_ms = settle_ms
        self._user_agent = user_agent
        self._channel = channel
        self._pin_dns = pin_dns
        self._launch_timeout_s = launch_timeout_seconds
        # The isolated worker passes an explicit allowlist so Chromium never
        # inherits the worker auth token (or any accidentally injected secret).
        # ``None`` preserves the normal environment for local development.
        self._browser_environment = (
            dict(browser_environment) if browser_environment is not None else None
        )
        self._plan: LaunchPlan | None = None
        self._max_concurrent = max(1, max_concurrent)
        # Created lazily on first capture so it binds to the running event loop.
        self._gate: asyncio.Semaphore | None = None

    def _launch_gate(self) -> asyncio.Semaphore:
        if self._gate is None:
            self._gate = asyncio.Semaphore(self._max_concurrent)
        return self._gate

    def apply_timing(self, *, timeout_seconds: float, settle_ms: int) -> None:
        """Update capture timing so changes to the runtime settings take effect
        on the next capture without a restart."""
        self._timeout_ms = int(timeout_seconds * 1000)
        self._settle_ms = settle_ms

    async def capture(
        self,
        *,
        url: str,
        css_selector: str | None = None,
        interaction_steps: list[dict[str, Any]] | None = None,
        timing: CaptureTiming | None = None,
    ) -> str | CapturedPage:
        from playwright.async_api import Error as PlaywrightError

        steps = [InteractionStep.from_dict(step) for step in interaction_steps or []]
        timing = timing or CaptureTiming(self._timeout_ms / 1000, self._settle_ms)
        resolver_arg = await self._dns_pin_arg(url)
        try:
            # Hold a launch permit only around the browser's lifetime so a burst of
            # concurrent captures queues instead of each spawning a Chromium at once.
            async with self._launch_gate():
                return await self._run_capture(url, css_selector, steps, resolver_arg, timing)
        except TimeoutError as exc:
            raise CaptureError(f"browser launch timed out for {url}: {exc}") from exc
        except BrowserUnavailable as exc:
            raise CaptureError(str(exc)) from exc
        except PlaywrightError as exc:
            detail = _redact_step_values(str(exc), steps)
            raise CaptureError(f"failed to capture {url}: {detail}") from exc

    async def _run_capture(
        self,
        url: str,
        css_selector: str | None,
        steps: list[InteractionStep],
        resolver_arg: str | None,
        timing: CaptureTiming,
    ) -> CapturedPage:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            # Bound launch and detection so a wedged browser binary can't hang
            # the (serial) scheduler tick forever — convert it to a transient.
            if self._plan is None:
                async with asyncio.timeout(self._launch_timeout_s):
                    self._plan = await resolve_launch_plan(
                        playwright, forced=self._channel, headless=True
                    )
            launch_kwargs = dict(self._plan.launch_kwargs)
            if resolver_arg:
                launch_kwargs["args"] = [*launch_kwargs.get("args", []), resolver_arg]
            if self._browser_environment is not None:
                launch_kwargs["env"] = self._browser_environment
            browser = None
            network_guard: BrowserNetworkGuard | None = None
            try:
                async with asyncio.timeout(self._launch_timeout_s):
                    browser = await playwright.chromium.launch(headless=True, **launch_kwargs)
                    context = await browser.new_context(
                        **hardened_context_options(user_agent=self._user_agent)
                    )
                    network_guard = BrowserNetworkGuard()
                    await network_guard.install(context)
                    page = await context.new_page()
                    network_guard.attach_page(page)
                    network_guard.reject_future_pages(context)
                document_status: int | None = None

                def track_document_response(response: Any) -> None:
                    nonlocal document_status
                    if (
                        response.request.is_navigation_request()
                        and response.frame == page.main_frame
                    ):
                        document_status = response.status

                page.on("response", track_document_response)
                page.set_default_timeout(int(timing.timeout_seconds * 1000))
                # "domcontentloaded" + an explicit settle, not "networkidle":
                # ad/analytics-heavy pages never go idle and would burn the whole
                # timeout (and then fail) on every check.
                response = await page.goto(url, wait_until="domcontentloaded")
                if response is None:
                    raise CaptureError("navigation returned no HTTP response")
                if response.status >= 400:
                    raise CaptureHttpError(response.status)
                await _assert_network_allowed(network_guard)
                await _reject_non_public_redirect(page.url)
                for step in steps:
                    await self._replay(page, step)
                    await _assert_network_allowed(network_guard)
                    if document_status is not None and document_status >= 400:
                        raise CaptureHttpError(document_status)
                # An interaction step can navigate the page; re-check before reading.
                await _reject_non_public_redirect(page.url)
                await page.wait_for_timeout(timing.settle_ms)
                await _assert_network_allowed(network_guard)
                if document_status is not None and document_status >= 400:
                    raise CaptureHttpError(document_status)
                await self._raise_if_blocked(page)
                content = await self._read_content(page, css_selector)
                await _assert_network_allowed(network_guard)
                if document_status is not None and document_status >= 400:
                    raise CaptureHttpError(document_status)
                return content
            except PlaywrightError as exc:
                if network_guard is not None:
                    try:
                        await _assert_network_allowed(network_guard)
                    except CaptureBlocked as blocked:
                        raise blocked from exc
                raise
            finally:
                if network_guard is not None:
                    await network_guard.aclose()
                if browser is not None:
                    await browser.close()

    async def _dns_pin_arg(self, url: str) -> str | None:
        """Resolve+validate the host now and return a Chromium ``--host-resolver-rules``
        arg pinning it to the vetted IP, so the browser connects to the exact address
        validation approved (closes the resolve-time-vs-connect-time rebind window).
        Returns ``None`` when pinning is off or the host is already an IP literal."""
        if not self._pin_dns:
            return None
        host = urlsplit(url).hostname
        if not host or _is_ip_literal(host):
            return None
        try:
            _url, ips = await resolve_public_url(url)
        except UnresolvableHost as exc:
            raise CaptureError(f"could not resolve {url}: {exc}") from exc
        except InvalidRequest as exc:
            raise CaptureBlocked(f"refusing to capture a non-public address: {exc}") from exc
        return f"--host-resolver-rules=MAP {host} {ips[0]}" if ips else None

    async def _read_content(self, page: Any, css_selector: str | None) -> CapturedPage:
        if not css_selector:
            payload = await page.evaluate(
                "() => ({html: document.documentElement.outerHTML, base_url: document.baseURI})"
            )
        else:
            locator = page.locator(css_selector)
            if await locator.count() == 0:
                raise CaptureSelectorMissing(f"selector {css_selector!r} matched nothing")
            # Keep the selected wrapper and read its base in the same document:
            # a navigation between two browser calls must not mix their metadata.
            payload = await locator.first.evaluate(
                "element => ({html: element.outerHTML, base_url: element.ownerDocument.baseURI})"
            )
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("html"), str)
            or not isinstance(payload.get("base_url"), str)
        ):
            raise CaptureError("browser returned invalid captured content")
        return CapturedPage(html=_cap(payload["html"]), base_url=payload["base_url"])

    @staticmethod
    async def _raise_if_blocked(page: Any) -> None:
        title = (await page.title()).lower()
        body = (await page.locator("body").inner_text())[:4000].lower()
        haystack = f"{title}\n{body}"
        if any(marker in haystack for marker in _BLOCK_MARKERS):
            raise CaptureBlocked("page returned a bot-protection interstitial")

    @staticmethod
    async def _replay(page: Any, step: InteractionStep) -> None:
        if step.action == "wait":
            await page.wait_for_timeout(step.timeout_ms)
        elif step.action == "wait_for" and step.selector:
            await page.locator(step.selector).first.wait_for(timeout=step.timeout_ms)
        elif step.action == "click" and step.selector:
            await page.locator(step.selector).first.click(timeout=step.timeout_ms)
        elif step.action == "fill" and step.selector:
            if step.value is None:
                raise CaptureError("a fill interaction is missing its resolved secret")
            if step.allowed_origin is None:
                raise CaptureBlocked("a fill interaction has no approved origin")
            handle = await page.locator(step.selector).first.element_handle(timeout=step.timeout_ms)
            if handle is None:
                raise CaptureError("a fill interaction matched no element")
            try:
                frame = await handle.owner_frame()
                if frame is None or not _fill_origin_allowed(
                    page.url, frame.url, step.allowed_origin
                ):
                    raise CaptureBlocked("a fill interaction reached an unapproved origin")
                # Use the checked handle, not a locator that could resolve again
                # in a different document if the page navigates before filling.
                await handle.fill(step.value, timeout=step.timeout_ms)
            finally:
                await handle.dispose()
        else:
            raise CaptureError(f"unsupported interaction step: {step.action!r}")


def _fill_origin_allowed(page_url: str, frame_url: str, approved: str) -> bool:
    try:
        return http_origin(page_url) == http_origin(frame_url) == http_origin(approved)
    except ValueError:
        return False


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _redact_step_values(message: str, steps: list[InteractionStep]) -> str:
    values = {step.value for step in steps if step.action == "fill" and step.value}
    for value in sorted(values, key=len, reverse=True):
        message = message.replace(value, "[REDACTED]")
    return message


async def _reject_non_public_redirect(final_url: str) -> None:
    """Re-validate the URL the browser actually landed on after a navigation.

    Defense-in-depth that catches a redirect to a literal-IP or blocked-name
    internal target. DNS rebinding for the *original* host is handled separately
    by pinning the connection to the vetted IP (``_dns_pin_arg``); this hostname
    re-check does not by itself prevent rebinding. The failure is non-transient,
    so the content is never read or stored.
    """
    try:
        await validate_public_url(final_url)
    except InvalidRequest as exc:
        raise CaptureBlocked(f"navigation reached a non-public address: {exc}") from exc


async def _assert_network_allowed(guard: BrowserNetworkGuard) -> None:
    try:
        await guard.checkpoint()
    except BrowserNetworkBlocked as exc:
        raise CaptureBlocked(str(exc)) from exc


async def capture_with_retry(
    capturer: PageCapturer,
    *,
    url: str,
    css_selector: str | None = None,
    interaction_steps: list[dict[str, Any]] | None = None,
    timing: CaptureTiming | None = None,
    attempts: int = 2,
    backoff_seconds: float = 1.0,
) -> str | CapturedPage:
    """Capture once, retrying only *transient* failures with a short backoff."""
    last_error: CaptureError | None = None
    for attempt in range(1, attempts + 1):
        try:
            if timing is not None and isinstance(capturer, SupportsCaptureTiming):
                return await capturer.capture(
                    url=url,
                    css_selector=css_selector,
                    interaction_steps=interaction_steps,
                    timing=timing,
                )
            return await capturer.capture(
                url=url, css_selector=css_selector, interaction_steps=interaction_steps
            )
        except CaptureError as exc:
            if not exc.transient:
                raise
            last_error = exc
            if attempt < attempts:
                await asyncio.sleep(backoff_seconds * attempt)
    assert last_error is not None
    raise last_error
