"""Reject cross-origin state-changing requests.

Because sessions live in cookies, a malicious page could try to ride a logged-in
user's cookie with a forged POST. SameSite=Lax already blocks most of that; this
guard closes the gap by refusing any mutating ``/api`` request whose ``Origin``
or ``Referer`` is not the application's own, or that the browser itself marks as
cross-site. Requests with neither header (non-browser clients that do not carry
the cookie automatically) are allowed through.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from driftwatch.api.error_contract import error_response
from driftwatch.config import Settings

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class OriginGuard:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self._app = app
        self._settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            request = Request(scope, receive)
            if self._should_check(request) and not self._is_same_origin(request):
                response = error_response(
                    request,
                    status_code=403,
                    detail="Cross-origin request rejected",
                    error_code="cross_origin_request",
                )
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)

    def _should_check(self, request: Request) -> bool:
        return request.method not in _SAFE_METHODS and request.url.path.startswith("/api")

    def _is_same_origin(self, request: Request) -> bool:
        if request.headers.get("sec-fetch-site") == "cross-site":
            return False
        allowed = self._settings.allowed_origins() | {self._request_origin(request)}
        origin = request.headers.get("origin")
        if origin:
            return origin.rstrip("/") in allowed
        referer = request.headers.get("referer")
        if referer:
            return _origin_of(referer) in allowed
        return True

    @staticmethod
    def _request_origin(request: Request) -> str:
        host = request.headers.get("host", "")
        return f"{request.url.scheme}://{host}" if host else ""


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
