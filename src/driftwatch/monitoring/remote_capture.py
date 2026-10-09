"""HTTP adapter for the isolated browser-capture service.

The main application resolves encrypted interaction values immediately before
this call. They cross the private service boundary in one authenticated request
and are never included in adapter logs or error messages.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, NoReturn
from uuid import uuid4

import httpx
from pydantic import SecretStr

from driftwatch.monitoring.capture import (
    CaptureBlocked,
    CapturedPage,
    CaptureError,
    CaptureHttpError,
    CaptureSelectorMissing,
    CaptureTiming,
)


class CaptureWorkerRejected(CaptureError):
    """The worker rejected a request that retrying cannot repair."""

    transient = False


@dataclass(frozen=True, slots=True)
class CaptureWorkerStatus:
    active: int
    queued: int
    active_capacity: int
    queue_capacity: int


class RemotePageCapturer:
    """Send capture jobs to a browser-only service over a private network."""

    def __init__(
        self,
        *,
        service_url: str,
        token: str,
        timeout_seconds: float,
        max_request_bytes: int,
        max_response_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = SecretStr(token)
        self._max_request_bytes = max_request_bytes
        self._max_response_bytes = max_response_bytes
        self._timing: CaptureTiming | None = None
        self._client = httpx.AsyncClient(
            base_url=service_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            headers={"Accept": "application/json", "Accept-Encoding": "identity"},
        )

    def apply_timing(self, *, timeout_seconds: float, settle_ms: int) -> None:
        self._timing = CaptureTiming(timeout_seconds, settle_ms)

    async def capture(
        self,
        *,
        url: str,
        css_selector: str | None = None,
        interaction_steps: list[dict[str, Any]] | None = None,
        timing: CaptureTiming | None = None,
    ) -> CapturedPage:
        timing = timing or self._timing
        try:
            encoded = json.dumps(
                {
                    "url": url,
                    "css_selector": css_selector,
                    "interaction_steps": interaction_steps or [],
                    "timeout_seconds": timing.timeout_seconds if timing else None,
                    "settle_ms": timing.settle_ms if timing else None,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise CaptureWorkerRejected("Capture request is not serializable") from exc
        if len(encoded) > self._max_request_bytes:
            raise CaptureWorkerRejected("Capture request exceeds the worker limit")

        headers = self._headers(content_type="application/json")
        try:
            async with self._client.stream(
                "POST", "/v1/capture", content=encoded, headers=headers
            ) as response:
                body = await _read_limited(response, self._max_response_bytes)
        except httpx.TimeoutException as exc:
            raise CaptureError("Capture worker timed out") from exc
        except httpx.HTTPError as exc:
            raise CaptureError("Capture worker is unavailable") from exc

        if response.status_code == httpx.codes.OK:
            try:
                payload = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CaptureError("Capture worker returned an invalid response") from exc
            html = payload.get("html") if isinstance(payload, dict) else None
            base_url = payload.get("base_url") if isinstance(payload, dict) else None
            if not isinstance(html, str) or not isinstance(base_url, str):
                raise CaptureError("Capture worker returned an invalid response")
            return CapturedPage(html=html, base_url=base_url)

        http_status = _http_status(body)
        if _error_code(body) == "http_error" and http_status is not None:
            raise CaptureHttpError(http_status)
        _raise_worker_error(_error_code(body), response.status_code)

    async def probe(self) -> CaptureWorkerStatus:
        """Verify the authenticated worker control path and return real load."""
        try:
            async with self._client.stream(
                "GET",
                "/readyz",
                headers=self._headers(),
                timeout=5.0,
            ) as response:
                body = await _read_limited(response, 65_536)
        except httpx.HTTPError as exc:
            raise CaptureError("Capture worker readiness probe failed") from exc
        if response.status_code != httpx.codes.OK:
            _raise_worker_error(_error_code(body), response.status_code)
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict) or payload.get("status") != "ok":
                raise ValueError
            values = tuple(
                _nonnegative_int(payload, key)
                for key in ("active", "queued", "active_capacity", "queue_capacity")
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            raise CaptureError("Capture worker returned an invalid readiness response") from exc
        active, queued, active_capacity, queue_capacity = values
        if active > active_capacity or queued > queue_capacity or active_capacity < 1:
            raise CaptureError("Capture worker returned an invalid readiness response")
        return CaptureWorkerStatus(active, queued, active_capacity, queue_capacity)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self, *, content_type: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._token.get_secret_value()}",
            "X-Request-ID": str(uuid4()),
        }
        if content_type is not None:
            headers["Content-Type"] = content_type
        return headers


async def _read_limited(response: httpx.Response, maximum: int) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > maximum:
                raise CaptureWorkerRejected("Capture worker response exceeds the limit")
        except ValueError as exc:
            raise CaptureError("Capture worker returned an invalid response") from exc

    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > maximum:
            raise CaptureWorkerRejected("Capture worker response exceeds the limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _error_code(body: bytes) -> str:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
        return ""
    code = payload["error"].get("code")
    return code if isinstance(code, str) else ""


def _http_status(body: bytes) -> int | None:
    try:
        payload = json.loads(body)
        value = payload["error"]["http_status"]
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, KeyError):
        return None
    return value if type(value) is int and 400 <= value <= 599 else None


def _nonnegative_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(key)
    return value


def _raise_worker_error(code: str, status_code: int) -> NoReturn:
    if code == "selector_missing":
        raise CaptureSelectorMissing("The configured selector matched no content")
    if code == "blocked":
        raise CaptureBlocked("Capture was blocked by the worker network policy")
    if code in {"invalid_request", "payload_too_large", "result_too_large"}:
        raise CaptureWorkerRejected("Capture request was rejected by the worker")
    if code == "unauthorized" or status_code in {
        httpx.codes.UNAUTHORIZED,
        httpx.codes.FORBIDDEN,
    }:
        raise CaptureWorkerRejected("Capture worker authentication failed")
    if code == "busy" or status_code == httpx.codes.TOO_MANY_REQUESTS:
        raise CaptureError("Capture worker is at capacity")
    if code == "timeout" or status_code == httpx.codes.GATEWAY_TIMEOUT:
        raise CaptureError("Capture worker timed out")
    raise CaptureError("Capture worker failed")
