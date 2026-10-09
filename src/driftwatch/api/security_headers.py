"""Add security headers to every response.

The SPA loads only same-origin assets and a single same-origin bootstrap script
(``/theme-init.js``), so a strict ``script-src 'self'`` holds without inline
script. Inline *styles* are allowed because the UI libraries set style
attributes; that is a far smaller risk than inline script.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "base-uri 'none'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "img-src 'self' data:",
        "style-src 'self' 'unsafe-inline'",
        "script-src 'self'",
        "connect-src 'self'",
        "font-src 'self'",
        "form-action 'self'",
    )
)
PERMISSIONS_POLICY = "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
HSTS = "max-age=63072000; includeSubDomains"


class SecurityHeaders:
    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self._app = app
        self._hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        is_api = scope.get("path", "").startswith("/api")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
                headers["Permissions-Policy"] = PERMISSIONS_POLICY
                headers["Server"] = "Driftwatch"  # overwrite the framework banner
                if self._hsts:
                    headers["Strict-Transport-Security"] = HSTS
                if is_api and "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self._app(scope, receive, send_with_headers)
