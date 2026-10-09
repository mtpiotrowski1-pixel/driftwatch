"""Security and reliability contract for the isolated browser worker."""

from __future__ import annotations

import asyncio
import html
import logging
from typing import Any
from urllib.parse import quote

import httpx
import pytest
from pydantic import ValidationError

from driftwatch.capture_worker import (
    _FORBIDDEN_APPLICATION_ENV,
    CaptureWorkerSettings,
    _browser_environment,
    create_capture_worker_app,
)
from driftwatch.monitoring.capture import (
    CaptureBlocked,
    CapturedPage,
    CaptureError,
    CaptureHttpError,
    CaptureSelectorMissing,
    CaptureTiming,
)
from driftwatch.monitoring.remote_capture import (
    CaptureWorkerRejected,
    CaptureWorkerStatus,
    RemotePageCapturer,
)

_TOKEN = "capture-worker-token-0123456789-abcdef"
_URL = "https://example.test/private?customer=acme"


@pytest.fixture(autouse=True)
def _worker_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model the dedicated container, which receives no application secrets."""
    for name in _FORBIDDEN_APPLICATION_ENV:
        monkeypatch.delenv(name, raising=False)


class StubCapturer:
    def __init__(
        self, *, result: str | CapturedPage = "<main>ok</main>", error: Exception | None = None
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def capture(self, **kwargs: Any) -> str | CapturedPage:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class BlockingCapturer(StubCapturer):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def capture(self, **kwargs: Any) -> str | CapturedPage:
        self.calls.append(kwargs)
        self.started.set()
        await self.release.wait()
        return self.result


def _settings(**overrides: Any) -> CaptureWorkerSettings:
    return CaptureWorkerSettings(token=_TOKEN, **overrides)


def _payload(*, value: str | None = None) -> dict[str, object]:
    steps: list[dict[str, object]] = []
    if value is not None:
        steps.append(
            {
                "action": "fill",
                "selector": "#password",
                "value": value,
                "allowed_origin": "https://example.test",
                "timeout_ms": 1_000,
            }
        )
    return {"url": _URL, "css_selector": "main", "interaction_steps": steps}


def _headers(token: str = _TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_worker_liveness_does_not_require_the_service_token() -> None:
    app = create_capture_worker_app(_settings(), capturer=StubCapturer())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://worker"
    ) as client:
        response = await client.get("/livez")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_worker_readiness_requires_auth_and_reports_real_capacity() -> None:
    app = create_capture_worker_app(
        _settings(max_concurrent=2, max_queued=3),
        capturer=StubCapturer(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://worker"
    ) as client:
        unauthorized = await client.get("/readyz")
        ready = await client.get("/readyz", headers=_headers())

    assert unauthorized.status_code == 401
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ok",
        "active": 0,
        "queued": 0,
        "active_capacity": 2,
        "queue_capacity": 3,
    }


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic wrong"},
        {"Authorization": "Bearer wrong"},
        {"Authorization": f"Bearer {_TOKEN} trailing"},
    ],
)
async def test_worker_rejects_invalid_auth_without_calling_browser(
    headers: dict[str, str],
) -> None:
    capturer = StubCapturer()
    app = create_capture_worker_app(_settings(), capturer=capturer)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://worker"
    ) as client:
        response = await client.post("/v1/capture", json=_payload(), headers=headers)

    assert response.status_code == 401
    assert response.json()["error"] == {"code": "unauthorized"}
    assert capturer.calls == []


async def test_worker_rejects_duplicate_authorization_headers() -> None:
    capturer = StubCapturer()
    app = create_capture_worker_app(_settings(), capturer=capturer)
    headers = [("Authorization", f"Bearer {_TOKEN}"), ("Authorization", f"Bearer {_TOKEN}")]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://worker"
    ) as client:
        response = await client.post("/v1/capture", json=_payload(), headers=headers)

    assert response.status_code == 401
    assert capturer.calls == []


async def test_worker_passes_fill_value_transiently_and_redacts_it_from_result() -> None:
    secret = "p@ss<&word"
    variants = (secret, html.escape(secret, quote=True), quote(secret, safe=""))
    capturer = StubCapturer(result="|".join(variants))
    app = create_capture_worker_app(_settings(), capturer=capturer)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://worker"
    ) as client:
        response = await client.post("/v1/capture", json=_payload(value=secret), headers=_headers())

    assert response.status_code == 200
    assert response.json()["html"] == "[REDACTED]|[REDACTED]|[REDACTED]"
    assert capturer.calls[0]["interaction_steps"][0]["value"] == secret
    assert all(variant not in response.text for variant in variants)


async def test_worker_validation_error_never_reflects_fill_value() -> None:
    secret = "malformed-secret-value"
    body = (
        '{"url":"https://example.test","interaction_steps":['
        f'{{"action":"fill","selector":"#x","value":"{secret}","timeout_ms":"bad"}}]}}'
    )
    app = create_capture_worker_app(_settings(), capturer=StubCapturer())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://worker"
    ) as client:
        response = await client.post(
            "/v1/capture",
            content=body,
            headers={**_headers(), "Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json()["error"] == {"code": "invalid_request"}
    assert secret not in response.text


async def test_worker_caps_request_and_response_sizes() -> None:
    app = create_capture_worker_app(
        _settings(max_request_bytes=1_024, max_response_bytes=65_536),
        capturer=StubCapturer(result="x" * 70_000),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://worker"
    ) as client:
        too_large_request = await client.post(
            "/v1/capture",
            content=b"x" * 1_025,
            headers={**_headers(), "Content-Type": "application/json"},
        )
        too_large_result = await client.post("/v1/capture", json=_payload(), headers=_headers())

    assert too_large_request.status_code == 413
    assert too_large_request.json()["error"] == {"code": "payload_too_large"}
    assert too_large_result.status_code == 413
    assert too_large_result.json()["error"] == {"code": "result_too_large"}


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (CaptureSelectorMissing(f"selector missing at {_URL}"), 422, "selector_missing"),
        (CaptureBlocked(f"private redirect from {_URL}"), 403, "blocked"),
    ],
)
async def test_worker_maps_expected_failures_without_exposing_details(
    error: Exception, status_code: int, code: str
) -> None:
    app = create_capture_worker_app(_settings(), capturer=StubCapturer(error=error))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://worker"
    ) as client:
        response = await client.post("/v1/capture", json=_payload(), headers=_headers())

    assert response.status_code == status_code
    assert response.json()["error"] == {"code": code}
    assert _URL not in response.text


@pytest.mark.parametrize("error", [CaptureError, RuntimeError])
async def test_worker_never_logs_or_returns_exception_secrets(
    error: type[Exception], caplog: pytest.LogCaptureFixture
) -> None:
    secret = "filled-password-from-vault"
    capturer = StubCapturer(error=error(f"{_URL} {secret}"))
    app = create_capture_worker_app(_settings(), capturer=capturer)
    with caplog.at_level(logging.WARNING, logger="driftwatch.capture_worker"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://worker"
        ) as client:
            response = await client.post(
                "/v1/capture", json=_payload(value=secret), headers=_headers()
            )

    evidence = response.text + caplog.text
    assert response.status_code in {500, 502}
    assert secret not in evidence
    assert _URL not in evidence


async def test_worker_bounds_the_waiting_queue() -> None:
    capturer = BlockingCapturer()
    app = create_capture_worker_app(
        _settings(max_concurrent=1, max_queued=1, timeout_seconds=5), capturer=capturer
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://worker"
    ) as client:
        first = asyncio.create_task(client.post("/v1/capture", json=_payload(), headers=_headers()))
        await capturer.started.wait()
        second = asyncio.create_task(
            client.post("/v1/capture", json=_payload(), headers=_headers())
        )
        await asyncio.sleep(0.05)
        readiness = await client.get("/readyz", headers=_headers())
        overflow = await client.post("/v1/capture", json=_payload(), headers=_headers())
        capturer.release.set()
        first_response, second_response = await asyncio.gather(first, second)

    assert overflow.status_code == 429
    assert readiness.json()["active"] == 1
    assert readiness.json()["queued"] == 1
    assert overflow.json()["error"] == {"code": "busy"}
    assert first_response.status_code == second_response.status_code == 200
    assert len(capturer.calls) == 2


async def test_worker_enforces_hard_capture_deadline() -> None:
    capturer = BlockingCapturer()
    app = create_capture_worker_app(
        _settings(max_concurrent=1, max_queued=0, timeout_seconds=1), capturer=capturer
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://worker"
    ) as client:
        response = await client.post("/v1/capture", json=_payload(), headers=_headers())

    assert response.status_code == 504
    assert response.json()["error"] == {"code": "timeout"}


@pytest.mark.parametrize(
    "environment_name",
    [
        "DRIFTWATCH_DATABASE_URL",
        "DRIFTWATCH_STRIPE_SECRET_KEY",
        "DRIFTWATCH_STRIPE_WEBHOOK_SECRET",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
    ],
)
def test_worker_settings_refuse_application_secrets(
    monkeypatch: pytest.MonkeyPatch,
    environment_name: str,
) -> None:
    secret = "application-secret-that-must-not-leak"
    monkeypatch.setenv(environment_name, secret)

    with pytest.raises(ValidationError) as captured:
        _settings()

    assert environment_name in str(captured.value)
    assert secret not in str(captured.value)


def test_browser_environment_is_an_allowlist() -> None:
    environment = _browser_environment(
        {
            "PATH": "/usr/bin",
            "HOME": "/tmp",
            "DRIFTWATCH_CAPTURE_WORKER_TOKEN": _TOKEN,
            "DRIFTWATCH_DATABASE_URL": "postgresql://secret",
        }
    )

    assert environment == {"PATH": "/usr/bin", "HOME": "/tmp"}


async def test_remote_capturer_round_trip_and_error_mapping() -> None:
    success_app = create_capture_worker_app(_settings(), capturer=StubCapturer())
    remote = RemotePageCapturer(
        service_url="http://worker",
        token=_TOKEN,
        timeout_seconds=2,
        max_request_bytes=65_536,
        max_response_bytes=65_536,
        transport=httpx.ASGITransport(app=success_app),
    )
    result = await remote.capture(url=_URL)
    assert result.html == "<main>ok</main>"
    assert result.base_url == _URL
    assert await remote.probe() == CaptureWorkerStatus(0, 0, 2, 4)
    await remote.aclose()

    blocked_app = create_capture_worker_app(
        _settings(), capturer=StubCapturer(error=CaptureBlocked("secret detail"))
    )
    blocked_remote = RemotePageCapturer(
        service_url="http://worker",
        token=_TOKEN,
        timeout_seconds=2,
        max_request_bytes=65_536,
        max_response_bytes=65_536,
        transport=httpx.ASGITransport(app=blocked_app),
    )
    with pytest.raises(CaptureBlocked, match="network policy"):
        await blocked_remote.capture(url=_URL)
    await blocked_remote.aclose()


async def test_remote_capturer_maps_auth_and_local_request_limits() -> None:
    app = create_capture_worker_app(_settings(), capturer=StubCapturer())
    wrong_token = RemotePageCapturer(
        service_url="http://worker",
        token="wrong-token",
        timeout_seconds=2,
        max_request_bytes=65_536,
        max_response_bytes=65_536,
        transport=httpx.ASGITransport(app=app),
    )
    with pytest.raises(CaptureWorkerRejected, match="authentication"):
        await wrong_token.capture(url=_URL)
    await wrong_token.aclose()

    bounded = RemotePageCapturer(
        service_url="http://worker",
        token=_TOKEN,
        timeout_seconds=2,
        max_request_bytes=10,
        max_response_bytes=65_536,
        transport=httpx.ASGITransport(app=app),
    )
    with pytest.raises(CaptureWorkerRejected, match="request exceeds"):
        await bounded.capture(url=_URL)
    await bounded.aclose()


async def test_remote_capturer_carries_base_url_and_request_timing_without_shared_mutation() -> (
    None
):
    capturer = StubCapturer(result=CapturedPage("<span>9</span>", "https://example.test/assets/"))
    app = create_capture_worker_app(_settings(), capturer=capturer)
    remote = RemotePageCapturer(
        service_url="http://worker",
        token=_TOKEN,
        timeout_seconds=2,
        max_request_bytes=65_536,
        max_response_bytes=65_536,
        transport=httpx.ASGITransport(app=app),
    )
    results = await asyncio.gather(
        remote.capture(url=_URL, timing=CaptureTiming(10, 100)),
        remote.capture(url=_URL, timing=CaptureTiming(20, 200)),
    )
    await remote.aclose()
    assert all(result.base_url == "https://example.test/assets/" for result in results)
    assert {call["timing"] for call in capturer.calls} == {
        CaptureTiming(10, 100),
        CaptureTiming(20, 200),
    }


@pytest.mark.parametrize("http_status", [404, 503])
async def test_remote_capturer_preserves_http_error_retry_policy(http_status: int) -> None:
    app = create_capture_worker_app(
        _settings(), capturer=StubCapturer(error=CaptureHttpError(http_status))
    )
    remote = RemotePageCapturer(
        service_url="http://worker",
        token=_TOKEN,
        timeout_seconds=2,
        max_request_bytes=65_536,
        max_response_bytes=65_536,
        transport=httpx.ASGITransport(app=app),
    )
    try:
        with pytest.raises(CaptureHttpError) as failure:
            await remote.capture(url=_URL)
        assert failure.value.status_code == http_status
        assert failure.value.transient is (http_status == 503)
    finally:
        await remote.aclose()
