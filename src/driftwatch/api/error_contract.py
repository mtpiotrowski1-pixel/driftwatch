"""Stable API error envelopes and per-request correlation identifiers."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")

_HTTP_ERROR_CODES = {
    400: "bad_request",
    401: "authentication_required",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    408: "request_timeout",
    409: "conflict",
    410: "gone",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    428: "precondition_required",
    429: "rate_limited",
    503: "service_unavailable",
}


class RequestIdMiddleware:
    """Accept a safe caller trace ID or assign an opaque server-generated one."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = _request_id_from_headers(Headers(scope=scope)) or _generate_request_id()
        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        await self._app(scope, receive, send_with_request_id)


def request_id_for(request: Request) -> str:
    """Return the request correlation ID, creating one for standalone handlers."""

    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and _is_valid_request_id(request_id):
        return request_id
    request_id = _generate_request_id()
    request.state.request_id = request_id
    return request_id


def http_error_code(status_code: int) -> str:
    """Map HTTP status to a stable, message-independent machine code."""

    return _HTTP_ERROR_CODES.get(status_code, f"http_{status_code}")


def error_response(
    request: Request,
    *,
    status_code: int,
    detail: object,
    error_code: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build the single public error shape without trusting response headers."""

    request_id = request_id_for(request)
    response_headers = {
        key: value
        for key, value in (headers or {}).items()
        if key.lower() != REQUEST_ID_HEADER.lower()
    }
    response_headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        {
            "detail": jsonable_encoder(detail),
            "error_code": error_code,
            "request_id": request_id,
        },
        status_code=status_code,
        headers=response_headers,
    )


def _request_id_from_headers(headers: Headers) -> str | None:
    values = headers.getlist(REQUEST_ID_HEADER)
    if len(values) != 1 or not _is_valid_request_id(values[0]):
        return None
    return values[0]


def _is_valid_request_id(value: str) -> bool:
    return _REQUEST_ID_PATTERN.fullmatch(value) is not None


def _generate_request_id() -> str:
    return uuid.uuid4().hex
