"""Bound API request bodies before framework parsers allocate them."""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from driftwatch.api.error_contract import error_response

DEFAULT_API_BODY_BYTES = 2 * 1024 * 1024
BRANDING_BODY_BYTES = 9 * 1024 * 1024
# The restore endpoint accepts a raw stream and independently enforces this same
# limit after authentication; there is no multipart framing to budget for.
RESTORE_BODY_BYTES = 1024 * 1024 * 1024


class _PayloadTooLarge(Exception):
    pass


class RequestBodyLimit:
    """Reject declared and chunked API bodies above their endpoint budget."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api"):
            await self._app(scope, receive, send)
            return

        limit = request_body_limit(str(scope.get("path", "")))
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await _send_too_large(scope, receive, send, limit)
            return

        received = 0
        response_started = False
        too_large = False

        async def limited_receive() -> Message:
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    too_large = True
                    raise _PayloadTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            # Starlette's body parser translates receive-side exceptions into a
            # generic 400 response. Once our counter tripped, suppress that
            # internal response and replace it with the stable 413 below.
            if too_large:
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._app(scope, limited_receive, tracked_send)
        except _PayloadTooLarge:
            too_large = True
        if too_large:
            if response_started:
                # API handlers consume request bodies before starting their
                # response. Keep this defensive branch explicit for any future
                # streaming handler that violates that ordering.
                raise RuntimeError("request body limit exceeded after response start")
            await _send_too_large(scope, receive, send, limit)


def request_body_limit(path: str) -> int:
    if path == "/api/admin/restore":
        return RESTORE_BODY_BYTES
    if path.startswith("/api/branding/assets/"):
        return BRANDING_BODY_BYTES
    return DEFAULT_API_BODY_BYTES


def _declared_length(scope: Scope) -> int | None:
    values = [
        value for name, value in scope.get("headers", []) if name.lower() == b"content-length"
    ]
    if not values:
        return None
    # Uvicorn normally rejects conflicting Content-Length headers first. Treat
    # malformed or repeated values as oversized here so they never reach a body
    # parser if another ASGI server forwards them.
    if len(values) != 1:
        return RESTORE_BODY_BYTES + 1
    try:
        length = int(values[0].decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        return RESTORE_BODY_BYTES + 1
    return length if length >= 0 else RESTORE_BODY_BYTES + 1


async def _send_too_large(scope: Scope, receive: Receive, send: Send, limit: int) -> None:
    request = Request(scope, receive=receive)
    response = error_response(
        request,
        status_code=413,
        detail=f"Request body exceeds the {limit}-byte endpoint limit",
        error_code="payload_too_large",
    )
    await response(scope, receive, send)
