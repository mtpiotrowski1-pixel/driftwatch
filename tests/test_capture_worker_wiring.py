"""Application-side fail-closed wiring for browser isolation."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from driftwatch.app import _default_page_capturer, create_app
from driftwatch.config import Settings
from driftwatch.monitoring.capture import CaptureError, PlaywrightCapturer
from driftwatch.monitoring.remote_capture import RemotePageCapturer

_APP_KEY = "application-secret-key-0123456789-abcdef"
_ENCRYPTION_KEY = "encryption-secret-key-0123456789-abcdef"
_WORKER_KEY = "capture-worker-token-0123456789-abcdef"
_PUBLIC = {
    "host": "0.0.0.0",
    "base_url": "https://driftwatch.example.com",
    "session_secret_key": _APP_KEY,
    "encryption_key": _ENCRYPTION_KEY,
}


def test_public_app_without_capture_worker_fails_closed() -> None:
    settings = Settings(**_PUBLIC)

    with pytest.raises(RuntimeError, match="Public deployments require"):
        create_app(settings, enable_scheduler=False)


def test_local_app_defaults_to_in_process_playwright() -> None:
    settings = Settings(
        secret_key="local",
        host="127.0.0.1",
        base_url="http://localhost:8000",
    )

    assert isinstance(_default_page_capturer(settings), PlaywrightCapturer)


def test_public_in_process_capture_requires_explicit_opt_in() -> None:
    settings = Settings(capture_allow_in_process=True, **_PUBLIC)

    assert isinstance(_default_page_capturer(settings), PlaywrightCapturer)


async def test_public_app_uses_remote_capture_worker() -> None:
    settings = Settings(
        capture_worker_url="https://capture.internal",
        capture_worker_token=_WORKER_KEY,
        **_PUBLIC,
    )

    capturer = _default_page_capturer(settings)
    assert isinstance(capturer, RemotePageCapturer)
    await capturer.aclose()


async def test_capture_worker_outage_degrades_health_without_removing_api_routing(
    tmp_path: Path,
    analyzer: object,
    channel: object,
    picker: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/health.db",
        secret_key="local-health-secret",
        scheduler_enabled=False,
        run_migrations=True,
        base_url="http://localhost:8000",
    )
    remote = RemotePageCapturer(
        service_url="https://capture.internal",
        token=_WORKER_KEY,
        timeout_seconds=5,
        max_request_bytes=1024,
        max_response_bytes=1024,
    )

    async def unavailable(_: RemotePageCapturer) -> object:
        raise CaptureError("simulated worker outage")

    monkeypatch.setattr(RemotePageCapturer, "probe", unavailable)
    app = create_app(
        settings,
        capturer=remote,
        analyzer=analyzer,  # type: ignore[arg-type]
        channel=channel,  # type: ignore[arg-type]
        picker=picker,  # type: ignore[arg-type]
        enable_scheduler=False,
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=settings.base_url,
        ) as client,
    ):
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["routing_ready"] is True
    assert response.json()["dependencies"]["capture"] == "unavailable"


@pytest.mark.parametrize(
    "values",
    [
        {"capture_worker_url": "https://capture.internal"},
        {"capture_worker_token": _WORKER_KEY},
    ],
)
def test_capture_worker_url_and_token_are_atomic(values: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="must be configured together"):
        Settings(**_PUBLIC, **values)


def test_plain_http_worker_requires_explicit_private_transport_opt_in() -> None:
    with pytest.raises(ValueError, match="Plain HTTP"):
        Settings(
            capture_worker_url="http://capture-worker:8090",
            capture_worker_token=_WORKER_KEY,
            **_PUBLIC,
        )

    settings = Settings(
        capture_worker_url="http://capture-worker:8090",
        capture_worker_token=_WORKER_KEY,
        capture_worker_allow_insecure_http=True,
        **_PUBLIC,
    )
    assert settings.capture_worker_url == "http://capture-worker:8090"


def test_capture_worker_token_cannot_reuse_application_key() -> None:
    with pytest.raises(ValueError, match="must be distinct"):
        Settings(
            capture_worker_url="https://capture.internal",
            capture_worker_token=_APP_KEY,
            **_PUBLIC,
        )
