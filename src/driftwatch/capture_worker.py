"""Minimal ASGI service that owns Chromium and no application data plane.

Run this process in a separate container with only its service token and capture
settings. It deliberately does not import the application factory, database,
settings store, AI client, mailer, session signing, or encryption keyring.
"""

from __future__ import annotations

import asyncio
import hmac
import html
import json
import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from driftwatch.monitoring.browser import parse_channel
from driftwatch.monitoring.capture import (
    CaptureBlocked,
    CaptureContentTooLarge,
    CapturedPage,
    CaptureError,
    CaptureHttpError,
    CaptureSelectorMissing,
    CaptureTiming,
    PageCapturer,
    PlaywrightCapturer,
)

logger = logging.getLogger(__name__)

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_FORBIDDEN_APPLICATION_ENV = frozenset(
    {
        "DATABASE_URL",
        "SECRET_KEY",
        "SESSION_SECRET_KEY",
        "SESSION_SECRET_KEY_PREVIOUS",
        "ENCRYPTION_KEY",
        "ENCRYPTION_KEY_PREVIOUS",
        "INITIAL_ADMIN_PASSWORD",
        "OPENAI_API_KEY",
        "SMTP_PASSWORD",
        "BREVO_API_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "DRIFTWATCH_DATABASE_URL",
        "DRIFTWATCH_SECRET_KEY",
        "DRIFTWATCH_SESSION_SECRET_KEY",
        "DRIFTWATCH_SESSION_SECRET_KEY_PREVIOUS",
        "DRIFTWATCH_ENCRYPTION_KEY",
        "DRIFTWATCH_ENCRYPTION_KEY_PREVIOUS",
        "DRIFTWATCH_OPENAI_API_KEY",
        "DRIFTWATCH_SMTP_PASSWORD",
        "DRIFTWATCH_BREVO_API_KEY",
        "DRIFTWATCH_STRIPE_SECRET_KEY",
        "DRIFTWATCH_STRIPE_WEBHOOK_SECRET",
        "DRIFTWATCH_INITIAL_ADMIN_PASSWORD",
    }
)
_BROWSER_ENV_ALLOWLIST = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "PLAYWRIGHT_BROWSERS_PATH",
        "TMPDIR",
        "TZ",
    }
)


class CaptureWorkerSettings(BaseSettings):
    """Worker-only configuration; no `.env` file is ever loaded."""

    model_config = SettingsConfigDict(
        env_prefix="DRIFTWATCH_CAPTURE_WORKER_",
        env_file=None,
        extra="ignore",
    )

    token: SecretStr
    host: str = "0.0.0.0"
    port: int = Field(default=8090, ge=1, le=65_535)
    timeout_seconds: float = Field(default=90.0, ge=1.0, le=300.0)
    max_request_bytes: int = Field(default=65_536, ge=1_024, le=2_097_152)
    max_response_bytes: int = Field(default=8_388_608, ge=65_536, le=33_554_432)
    max_concurrent: int = Field(default=2, ge=1, le=16)
    max_queued: int = Field(default=4, ge=0, le=64)
    capture_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    capture_settle_ms: int = Field(default=750, ge=0, le=30_000)
    capture_launch_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    capture_user_agent: str = Field(
        default="Mozilla/5.0 (compatible; DriftwatchCaptureWorker/1.0)",
        min_length=1,
        max_length=500,
    )
    capture_browser_channel: str = "chromium"
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _validate_boundary(self) -> CaptureWorkerSettings:
        if len(self.token.get_secret_value()) < 32:
            raise ValueError("Capture worker token must contain at least 32 characters")
        forbidden = sorted(
            name for name in os.environ if name.upper() in _FORBIDDEN_APPLICATION_ENV
        )
        if forbidden:
            raise ValueError(
                "Capture worker refuses application secret environment variables: "
                + ", ".join(forbidden)
            )
        return self


class WorkerInteractionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["click", "fill", "wait_for", "wait"]
    selector: str | None = Field(default=None, max_length=500)
    value: SecretStr | None = Field(default=None, max_length=32_768)
    allowed_origin: str | None = Field(default=None, max_length=2_048)
    timeout_ms: int = Field(default=10_000, ge=0, le=120_000)

    @model_validator(mode="after")
    def _validate_shape(self) -> WorkerInteractionStep:
        if self.action != "wait" and not (self.selector or "").strip():
            raise ValueError("This interaction requires a selector")
        if self.action == "fill" and self.value is None:
            raise ValueError("A fill interaction requires a resolved value")
        if self.action == "fill" and self.allowed_origin is None:
            raise ValueError("A fill interaction requires an approved origin")
        if self.action != "fill" and self.value is not None:
            raise ValueError("Only fill interactions may carry a value")
        return self

    def runtime_value(self) -> dict[str, object]:
        return {
            "action": self.action,
            "selector": self.selector,
            "value": self.value.get_secret_value() if self.value is not None else None,
            "allowed_origin": self.allowed_origin,
            "timeout_ms": self.timeout_ms,
        }


class WorkerCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2_048)
    css_selector: str | None = Field(default=None, max_length=500)
    interaction_steps: list[WorkerInteractionStep] = Field(default_factory=list, max_length=20)
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=120.0)
    settle_ms: int | None = Field(default=None, ge=0, le=30_000)

    def runtime_steps(self) -> list[dict[str, object]]:
        return [step.runtime_value() for step in self.interaction_steps]

    def fill_values(self) -> set[str]:
        return {
            step.value.get_secret_value()
            for step in self.interaction_steps
            if step.action == "fill" and step.value is not None and step.value.get_secret_value()
        }


class WorkerCapacityExceeded(Exception):
    """The bounded admission queue has no remaining slot."""


@dataclass(frozen=True, slots=True)
class WorkerCapacitySnapshot:
    active: int
    queued: int
    active_capacity: int
    queue_capacity: int


class BoundedCaptureAdmission:
    """Cap active browsers and waiting requests without spawning background jobs."""

    def __init__(self, *, max_concurrent: int, max_queued: int) -> None:
        self._permits = asyncio.Semaphore(max_concurrent)
        self._state_lock = asyncio.Lock()
        self._max_concurrent = max_concurrent
        self._max_queued = max_queued
        self._active = 0
        self._queued = 0

    async def acquire(self) -> None:
        queued = False
        async with self._state_lock:
            if not self._permits.locked():
                await self._permits.acquire()
                self._active += 1
                return
            if self._queued >= self._max_queued:
                raise WorkerCapacityExceeded
            self._queued += 1
            queued = True

        acquired = False
        try:
            await self._permits.acquire()
            acquired = True
        finally:
            if queued:
                # No await here: cancellation after acquiring a permit must not
                # strand queue accounting or hide an active browser.
                self._queued -= 1
                if acquired:
                    self._active += 1

    def release(self) -> None:
        if self._active <= 0:
            raise RuntimeError("capture admission accounting underflow")
        self._active -= 1
        self._permits.release()

    def snapshot(self) -> WorkerCapacitySnapshot:
        return WorkerCapacitySnapshot(
            active=self._active,
            queued=self._queued,
            active_capacity=self._max_concurrent,
            queue_capacity=self._max_queued,
        )


def create_capture_worker_app(
    settings: CaptureWorkerSettings | None = None,
    *,
    capturer: PageCapturer | None = None,
) -> FastAPI:
    resolved = settings or CaptureWorkerSettings()
    page_capturer = capturer or PlaywrightCapturer(
        timeout_seconds=resolved.capture_timeout_seconds,
        settle_ms=resolved.capture_settle_ms,
        user_agent=resolved.capture_user_agent,
        channel=parse_channel(resolved.capture_browser_channel),
        pin_dns=True,
        launch_timeout_seconds=resolved.capture_launch_timeout_seconds,
        max_concurrent=resolved.max_concurrent,
        browser_environment=_browser_environment(os.environ),
    )
    admission = BoundedCaptureAdmission(
        max_concurrent=resolved.max_concurrent,
        max_queued=resolved.max_queued,
    )

    app = FastAPI(
        title="Driftwatch capture worker",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/livez", include_in_schema=False)
    async def livez() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz(request: Request) -> Response:
        request_id = _request_id(request)
        if not _authorized(request, resolved.token):
            return _error("unauthorized", status.HTTP_401_UNAUTHORIZED, request_id)
        capacity = admission.snapshot()
        return JSONResponse(
            {
                "status": "ok",
                "active": capacity.active,
                "queued": capacity.queued,
                "active_capacity": capacity.active_capacity,
                "queue_capacity": capacity.queue_capacity,
            },
            headers={"X-Request-ID": request_id, "Cache-Control": "no-store"},
        )

    @app.post("/v1/capture", include_in_schema=False)
    async def capture(request: Request) -> Response:
        request_id = _request_id(request)
        if not _authorized(request, resolved.token):
            return _error("unauthorized", status.HTTP_401_UNAUTHORIZED, request_id)

        try:
            raw = await _read_request(request, resolved.max_request_bytes)
            payload = WorkerCaptureRequest.model_validate_json(raw)
        except WorkerRequestError as exc:
            return _error(exc.code, exc.status_code, request_id)
        except ValidationError:
            return _error("invalid_request", status.HTTP_422_UNPROCESSABLE_CONTENT, request_id)

        try:
            async with asyncio.timeout(resolved.timeout_seconds):
                try:
                    await admission.acquire()
                except WorkerCapacityExceeded:
                    return _error("busy", status.HTTP_429_TOO_MANY_REQUESTS, request_id)
                try:
                    content = await page_capturer.capture(
                        url=payload.url,
                        css_selector=payload.css_selector,
                        interaction_steps=payload.runtime_steps(),
                        timing=CaptureTiming(
                            timeout_seconds=(
                                payload.timeout_seconds
                                if payload.timeout_seconds is not None
                                else resolved.capture_timeout_seconds
                            ),
                            settle_ms=(
                                payload.settle_ms
                                if payload.settle_ms is not None
                                else resolved.capture_settle_ms
                            ),
                        ),
                    )
                finally:
                    admission.release()
        except TimeoutError:
            return _error("timeout", status.HTTP_504_GATEWAY_TIMEOUT, request_id)
        except CaptureSelectorMissing:
            return _error("selector_missing", status.HTTP_422_UNPROCESSABLE_CONTENT, request_id)
        except CaptureBlocked:
            return _error("blocked", status.HTTP_403_FORBIDDEN, request_id)
        except CaptureContentTooLarge:
            return _error("result_too_large", status.HTTP_413_CONTENT_TOO_LARGE, request_id)
        except CaptureHttpError as exc:
            return _error(
                "http_error", status.HTTP_502_BAD_GATEWAY, request_id, http_status=exc.status_code
            )
        except CaptureError as exc:
            _log_failure(request_id, "capture_failed", exc)
            return _error("capture_failed", status.HTTP_502_BAD_GATEWAY, request_id)
        except Exception as exc:
            _log_failure(request_id, "internal_error", exc)
            return _error("internal_error", status.HTTP_500_INTERNAL_SERVER_ERROR, request_id)

        result = (
            content if isinstance(content, CapturedPage) else CapturedPage(content, payload.url)
        )
        encoded = json.dumps(
            {
                "html": _redact_fill_values(result.html, payload.fill_values()),
                "base_url": _redact_fill_values(result.base_url, payload.fill_values()),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > resolved.max_response_bytes:
            return _error("result_too_large", status.HTTP_413_CONTENT_TOO_LARGE, request_id)
        return Response(
            encoded,
            status_code=status.HTTP_200_OK,
            media_type="application/json",
            headers={"X-Request-ID": request_id, "Cache-Control": "no-store"},
        )

    return app


class WorkerRequestError(Exception):
    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


async def _read_request(request: Request, maximum: int) -> bytes:
    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if content_type != "application/json":
        raise WorkerRequestError("invalid_request", status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError as exc:
            raise WorkerRequestError("invalid_request", status.HTTP_400_BAD_REQUEST) from exc
        if declared < 0:
            raise WorkerRequestError("invalid_request", status.HTTP_400_BAD_REQUEST)
        if declared > maximum:
            raise WorkerRequestError("payload_too_large", status.HTTP_413_CONTENT_TOO_LARGE)

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > maximum:
            raise WorkerRequestError("payload_too_large", status.HTTP_413_CONTENT_TOO_LARGE)
        chunks.append(chunk)
    return b"".join(chunks)


def _authorized(request: Request, expected: SecretStr) -> bool:
    values = request.headers.getlist("authorization")
    if len(values) != 1:
        return False
    scheme, separator, credential = values[0].partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not credential or " " in credential:
        return False
    return hmac.compare_digest(credential, expected.get_secret_value())


def _request_id(request: Request) -> str:
    values = request.headers.getlist("x-request-id")
    if len(values) == 1 and _REQUEST_ID.fullmatch(values[0]):
        return values[0]
    return str(uuid4())


def _error(
    code: str, status_code: int, request_id: str, *, http_status: int | None = None
) -> JSONResponse:
    error: dict[str, object] = {"code": code}
    if http_status is not None:
        error["http_status"] = http_status
    return JSONResponse(
        {"error": error, "request_id": request_id},
        status_code=status_code,
        headers={"X-Request-ID": request_id, "Cache-Control": "no-store"},
    )


def _log_failure(request_id: str, code: str, exc: Exception) -> None:
    # Never log str(exc): browser failures may include the URL or a fill value.
    logger.warning(
        "capture worker failure request_id=%s code=%s type=%s",
        request_id,
        code,
        type(exc).__name__,
    )


def _redact_fill_values(content: str, values: set[str]) -> str:
    redacted = content
    for value in sorted(values, key=len, reverse=True):
        variants = {value, html.escape(value, quote=True), quote(value, safe="")}
        for variant in sorted(variants, key=len, reverse=True):
            if variant:
                redacted = redacted.replace(variant, "[REDACTED]")
    return redacted


def _browser_environment(environ: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in environ.items() if key in _BROWSER_ENV_ALLOWLIST}


def _listen_port(settings: CaptureWorkerSettings) -> int:
    raw_port = os.environ.get("PORT")
    if raw_port is None:
        return settings.port
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError("Platform PORT must be an integer") from exc
    if not 1 <= port <= 65_535:
        raise ValueError("Platform PORT must be between 1 and 65535")
    return port


def run() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = CaptureWorkerSettings()
    logging.basicConfig(
        level=logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    uvicorn.run(
        create_capture_worker_app(settings),
        host=settings.host,
        port=_listen_port(settings),
        server_header=False,
        date_header=False,
        proxy_headers=False,
        access_log=True,
    )
