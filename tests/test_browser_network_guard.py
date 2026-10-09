"""Browser SSRF policy tests using Playwright-shaped doubles and no network."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from driftwatch.exceptions import InvalidRequest
from driftwatch.monitoring.browser import BrowserChannel
from driftwatch.monitoring.capture import CaptureBlocked, _assert_network_allowed
from driftwatch.monitoring.network_guard import (
    BrowserNetworkBlocked,
    BrowserNetworkGuard,
    hardened_context_options,
)
from driftwatch.monitoring.picker import PickerMode, PickerSession, PickerState


class FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url


class FakeRoute:
    def __init__(self, url: str) -> None:
        self.request = FakeRequest(url)
        self.continued = False
        self.aborted_with: str | None = None

    async def continue_(self) -> None:
        self.continued = True

    async def abort(self, error_code: str) -> None:
        self.aborted_with = error_code


class FakeWebSocketRoute:
    def __init__(self, url: str) -> None:
        self.url = url
        self.connected = False
        self.closed_with: tuple[int | None, str | None] | None = None

    async def connect_to_server(self) -> None:
        self.connected = True

    async def close(self, *, code: int | None = None, reason: str | None = None) -> None:
        self.closed_with = (code, reason)


class FakeDownload:
    def __init__(self) -> None:
        self.cancelled = False

    async def cancel(self) -> None:
        self.cancelled = True


class FakePage:
    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[Any], None]] = {}
        self.closed = False

    def on(self, event: str, handler: Callable[[Any], None]) -> None:
        self.handlers[event] = handler

    async def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self) -> None:
        self.http_handler: Callable[[FakeRoute], Awaitable[None]] | None = None
        self.websocket_handler: Callable[[FakeWebSocketRoute], Awaitable[None]] | None = None
        self.handlers: dict[str, Callable[[Any], None]] = {}
        self.install_order: list[str] = []

    async def route(self, pattern: str, handler: Callable[[FakeRoute], Awaitable[None]]) -> None:
        assert pattern == "**/*"
        self.install_order.append("http")
        self.http_handler = handler

    async def route_web_socket(
        self,
        pattern: str,
        handler: Callable[[FakeWebSocketRoute], Awaitable[None]],
    ) -> None:
        assert pattern == "**/*"
        self.install_order.append("websocket")
        self.websocket_handler = handler

    def on(self, event: str, handler: Callable[[Any], None]) -> None:
        self.handlers[event] = handler


def _validator(
    *, blocked_fragment: str = "private", seen: list[str] | None = None
) -> Callable[[str], Awaitable[str]]:
    async def validate(url: str) -> str:
        if seen is not None:
            seen.append(url)
        if blocked_fragment in url:
            raise InvalidRequest("non-public address")
        return url

    return validate


async def _installed_guard(
    *, validator: Callable[[str], Awaitable[str]] | None = None
) -> tuple[BrowserNetworkGuard, FakeContext]:
    guard = BrowserNetworkGuard(validate_url=validator or _validator())
    context = FakeContext()
    await guard.install(context)
    assert context.install_order == ["http", "websocket"]
    return guard, context


def test_context_options_disable_service_workers_and_download_storage() -> None:
    assert hardened_context_options(user_agent="Driftwatch/1") == {
        "accept_downloads": False,
        "service_workers": "block",
        "user_agent": "Driftwatch/1",
    }


async def test_public_subrequest_is_validated_before_it_is_continued() -> None:
    seen: list[str] = []
    guard, context = await _installed_guard(validator=_validator(seen=seen))
    route = FakeRoute("https://cdn.example.test/app.js")

    assert context.http_handler is not None
    await context.http_handler(route)
    await guard.checkpoint()

    assert seen == ["https://cdn.example.test/app.js"]
    assert route.continued
    assert route.aborted_with is None


async def test_redirect_hop_to_private_address_is_aborted_and_fails_capture() -> None:
    seen: list[str] = []
    guard, context = await _installed_guard(validator=_validator(seen=seen))
    first_hop = FakeRoute("https://public.example.test/redirect")
    private_hop = FakeRoute("http://private.example.test/metadata")

    assert context.http_handler is not None
    await context.http_handler(first_hop)
    await context.http_handler(private_hop)

    assert first_hop.continued
    assert private_hop.aborted_with == "blockedbyclient"
    assert seen == [first_hop.request.url, private_hop.request.url]
    with pytest.raises(BrowserNetworkBlocked, match="non-public"):
        await guard.checkpoint()


async def test_non_http_subrequest_is_rejected_without_calling_resolver() -> None:
    seen: list[str] = []
    guard, context = await _installed_guard(validator=_validator(seen=seen))
    route = FakeRoute("file:///etc/passwd")

    assert context.http_handler is not None
    await context.http_handler(route)

    assert seen == []
    assert route.aborted_with == "blockedbyclient"
    with pytest.raises(BrowserNetworkBlocked):
        await guard.checkpoint()


async def test_resolver_failure_aborts_without_logging_target(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_target = "https://customer-secret.example/app.js?token=secret"

    async def broken_validator(_url: str) -> str:
        raise OSError(f"resolver unavailable for {secret_target}")

    guard, context = await _installed_guard(validator=broken_validator)
    route = FakeRoute(secret_target)

    assert context.http_handler is not None
    with caplog.at_level(logging.WARNING, logger="driftwatch.monitoring.network_guard"):
        await context.http_handler(route)

    assert route.aborted_with == "blockedbyclient"
    assert "type=OSError" in caplog.text
    assert secret_target not in caplog.text
    assert "customer-secret" not in caplog.text
    with pytest.raises(BrowserNetworkBlocked, match="safely validated"):
        await guard.checkpoint()


async def test_websocket_uses_public_url_validation_before_connecting() -> None:
    seen: list[str] = []
    guard, context = await _installed_guard(validator=_validator(seen=seen))
    websocket = FakeWebSocketRoute("wss://stream.example.test/events")

    assert context.websocket_handler is not None
    await context.websocket_handler(websocket)
    await guard.checkpoint()

    assert seen == ["https://stream.example.test/events"]
    assert websocket.connected
    assert websocket.closed_with is None


async def test_private_websocket_is_closed_without_connecting() -> None:
    guard, context = await _installed_guard()
    websocket = FakeWebSocketRoute("ws://private.example.test/admin")

    assert context.websocket_handler is not None
    await context.websocket_handler(websocket)

    assert not websocket.connected
    assert websocket.closed_with == (1008, "Blocked by browser network policy")
    with pytest.raises(BrowserNetworkBlocked, match="WebSocket"):
        await guard.checkpoint()


async def test_download_is_cancelled_and_marks_the_session_invalid() -> None:
    guard = BrowserNetworkGuard(validate_url=_validator())
    page = FakePage()
    download = FakeDownload()
    guard.attach_page(page)

    page.handlers["download"](download)
    await guard.aclose()

    assert download.cancelled
    with pytest.raises(BrowserNetworkBlocked, match="downloads"):
        await guard.checkpoint()


async def test_popup_is_closed_and_marks_the_session_invalid() -> None:
    guard, context = await _installed_guard()
    popup = FakePage()
    guard.reject_future_pages(context)

    context.handlers["page"](popup)
    await guard.aclose()

    assert popup.closed
    with pytest.raises(BrowserNetworkBlocked, match="popups"):
        await guard.checkpoint()


async def test_capture_translates_policy_violation_to_non_transient_failure() -> None:
    guard, context = await _installed_guard()
    route = FakeRoute("http://private.example.test/metadata")

    assert context.http_handler is not None
    await context.http_handler(route)

    with pytest.raises(CaptureBlocked) as raised:
        await _assert_network_allowed(guard)
    assert raised.value.transient is False


async def test_picker_moves_to_error_after_policy_violation() -> None:
    guard, context = await _installed_guard()
    route = FakeRoute("http://private.example.test/metadata")
    session = PickerSession(
        session_id="test-session",
        url="https://example.test",
        mode=PickerMode.SELECT,
        channel=BrowserChannel.CHROMIUM,
        user_agent="Driftwatch/1",
        session_timeout=60,
        idle_timeout=30,
        owner_user_id=1,
    )
    session._network_guard = guard

    assert context.http_handler is not None
    await context.http_handler(route)

    assert not await session._network_allowed()
    assert session.status().state is PickerState.ERROR
    assert session.status().detail is not None
