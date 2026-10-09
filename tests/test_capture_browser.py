"""Real browser regressions against a test-owned local HTTP fixture.

Only the fixture origin is allowed by the injected test validator. Production
network policy is not relaxed, and these checks make no third-party requests.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import httpx
import pytest

import driftwatch.monitoring.capture as capture_module
from driftwatch.capture_worker import (
    _FORBIDDEN_APPLICATION_ENV,
    CaptureWorkerSettings,
    create_capture_worker_app,
)
from driftwatch.exceptions import InvalidRequest
from driftwatch.monitoring.capture import (
    CaptureBlocked,
    CapturedPage,
    CaptureHttpError,
    CaptureTiming,
    PlaywrightCapturer,
)
from driftwatch.monitoring.network_guard import BrowserNetworkGuard
from driftwatch.monitoring.remote_capture import RemotePageCapturer


class _FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/reports/page")
            self.end_headers()
            return
        status = int(path[1:]) if path in {"/404", "/503"} else 200
        if path == "/reports/page":
            body = (
                "<base href='../assets/'><span id='price'>9</span><a href='annual.pdf'>Report</a>"
            )
        elif path == "/delayed":
            body = (
                "<span id='price'>9</span><script>"
                "setTimeout(()=>document.querySelector('#price').textContent='12', 100)</script>"
            )
        elif path == "/login":
            body = (
                "<input id='password'><p id='result'>Empty</p><script>"
                "document.querySelector('#password').oninput=e=>"
                "document.querySelector('#result').textContent=e.target.value</script>"
            )
        elif path == "/click-error":
            body = "<a id='next' href='/503'>Next</a>"
        elif path == "/delayed-error":
            body = (
                "<p>Initial content</p><script>setTimeout(()=>location.href='/503', 100)</script>"
            )
        elif path == "/leave-origin":
            # localhost and 127.0.0.1 address the same fixture, but are distinct
            # HTTP origins. An approved-origin fill must reject the redirect.
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{self.server.server_port}/login")
            self.end_headers()
            return
        else:
            body = "<p>Service unavailable</p>"
        data = f"<html><body>{body}</body></html>".encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, _format: str, *args: object) -> None:
        pass


@pytest.fixture
def fixture_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    origin = f"http://127.0.0.1:{server.server_port}"

    async def allow_fixture(url: str) -> str:
        parsed = urlsplit(url)
        if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port != server.server_port:
            raise InvalidRequest("not the test fixture")
        return url

    monkeypatch.setattr(
        capture_module,
        "BrowserNetworkGuard",
        lambda: BrowserNetworkGuard(validate_url=allow_fixture),
    )
    monkeypatch.setattr(capture_module, "_reject_non_public_redirect", allow_fixture)
    try:
        yield origin
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


async def test_browser_retains_short_selected_wrapper_and_actual_document_base(
    fixture_url: str,
) -> None:
    capturer = PlaywrightCapturer(pin_dns=False, settle_ms=0)
    result = await capturer.capture(url=f"{fixture_url}/redirect", css_selector="#price")
    assert isinstance(result, CapturedPage)
    assert result.html == '<span id="price">9</span>'
    assert result.base_url == f"{fixture_url}/assets/"


@pytest.mark.parametrize("status", [404, 503])
async def test_browser_rejects_http_error_content(fixture_url: str, status: int) -> None:
    capturer = PlaywrightCapturer(pin_dns=False, settle_ms=0)
    with pytest.raises(CaptureHttpError) as failure:
        await capturer.capture(url=f"{fixture_url}/{status}")
    assert failure.value.status_code == status
    assert failure.value.transient is (status == 503)


async def test_browser_uses_per_request_timing(fixture_url: str) -> None:
    capturer = PlaywrightCapturer(pin_dns=False, settle_ms=0)
    result = await capturer.capture(
        url=f"{fixture_url}/delayed", css_selector="#price", timing=CaptureTiming(5, 350)
    )
    assert isinstance(result, CapturedPage)
    assert ">12<" in result.html


async def test_browser_only_fills_an_approved_origin(fixture_url: str) -> None:
    capturer = PlaywrightCapturer(pin_dns=False, settle_ms=0)
    steps = [
        {
            "action": "fill",
            "selector": "#password",
            "value": "synthetic-fixture-value",
            "allowed_origin": fixture_url,
        }
    ]
    result = await capturer.capture(url=f"{fixture_url}/login", interaction_steps=steps)
    assert isinstance(result, CapturedPage)
    assert "synthetic-fixture-value" in result.html
    with pytest.raises(CaptureBlocked, match="unapproved origin"):
        await capturer.capture(url=f"{fixture_url}/leave-origin", interaction_steps=steps)


async def test_browser_rejects_an_http_error_after_an_interaction(fixture_url: str) -> None:
    capturer = PlaywrightCapturer(pin_dns=False, settle_ms=0)
    with pytest.raises(CaptureHttpError) as failure:
        await capturer.capture(
            url=f"{fixture_url}/click-error",
            interaction_steps=[{"action": "click", "selector": "#next"}],
        )
    assert failure.value.status_code == 503


async def test_remote_worker_runs_real_browser_with_request_timing(
    fixture_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in _FORBIDDEN_APPLICATION_ENV:
        monkeypatch.delenv(name, raising=False)
    token = "synthetic-capture-token-0123456789abcdef"
    worker = create_capture_worker_app(
        CaptureWorkerSettings(token=token),
        capturer=PlaywrightCapturer(pin_dns=False, settle_ms=0),
    )
    remote = RemotePageCapturer(
        service_url="http://worker",
        token=token,
        timeout_seconds=10,
        max_request_bytes=65_536,
        max_response_bytes=65_536,
        transport=httpx.ASGITransport(app=worker),
    )
    try:
        result = await remote.capture(
            url=f"{fixture_url}/delayed",
            css_selector="#price",
            timing=CaptureTiming(5, 350),
        )
    finally:
        await remote.aclose()
    assert ">12<" in result.html
    assert result.base_url == f"{fixture_url}/delayed"


async def test_browser_rejects_an_http_error_during_settling(fixture_url: str) -> None:
    capturer = PlaywrightCapturer(pin_dns=False, settle_ms=500)
    with pytest.raises(CaptureHttpError) as failure:
        await capturer.capture(url=f"{fixture_url}/delayed-error")
    assert failure.value.status_code == 503
