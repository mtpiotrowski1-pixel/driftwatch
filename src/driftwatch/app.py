"""FastAPI application factory and process entry point.

``create_app`` is dependency-injectable: tests pass an in-memory database
through ``settings`` and fake the capturer, analyzer, and channel, so the whole
HTTP surface runs without a browser, an OpenAI key, or a mail server. Local
development defaults to in-process Playwright; public deployments fail closed
unless they use the isolated capture worker (or explicitly accept the risk).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from driftwatch import __version__
from driftwatch.account_mail import AccountEmailWorker
from driftwatch.api import (
    admin,
    audit,
    auth,
    billing,
    branding,
    changes,
    exports,
    health,
    notifications,
    operations,
    operators,
    organizations,
    plans,
    projects,
    recipients,
    sites,
    support_access,
    usage,
    users,
)
from driftwatch.api import (
    picker as picker_routes,
)
from driftwatch.api import (
    settings as settings_router,
)
from driftwatch.api.error_contract import (
    RequestIdMiddleware,
    error_response,
    http_error_code,
    request_id_for,
)
from driftwatch.api.origin import OriginGuard
from driftwatch.api.request_limits import RequestBodyLimit
from driftwatch.api.security_headers import SecurityHeaders
from driftwatch.billing.factory import build_billing_provider
from driftwatch.billing.provider import BillingProvider
from driftwatch.config import PROJECT_ROOT, Settings, get_settings
from driftwatch.db import Database
from driftwatch.exceptions import (
    AccessDenied,
    ConflictError,
    DriftwatchError,
    InvalidRequest,
    NotFoundError,
    PlanLimitReached,
)
from driftwatch.logging_setup import configure_logging
from driftwatch.maintenance import MaintenanceGate, MaintenanceMode
from driftwatch.monitoring.analyzer import ChangeAnalyzer
from driftwatch.monitoring.browser import parse_channel
from driftwatch.monitoring.capture import PageCapturer, PlaywrightCapturer
from driftwatch.monitoring.picker import PickerManager, PickerService
from driftwatch.monitoring.remote_capture import RemotePageCapturer
from driftwatch.notifications.email import EmailChannel
from driftwatch.runner import SiteRunner
from driftwatch.scheduler import MonitorScheduler
from driftwatch.security.crypto import SecretBox
from driftwatch.security.throttle import LoginThrottle
from driftwatch.seed import seed_admin

logger = logging.getLogger(__name__)

_CONTRACT_BY_ERROR: dict[type[DriftwatchError], tuple[int, str]] = {
    NotFoundError: (404, "not_found"),
    ConflictError: (409, "conflict"),
    AccessDenied: (403, "permission_denied"),
    PlanLimitReached: (403, "plan_limit_reached"),
    InvalidRequest: (400, "invalid_request"),
}


def _require_capture_runtime(settings: Settings) -> None:
    if settings.capture_worker_url or settings.is_local or settings.capture_allow_in_process:
        return
    raise RuntimeError(
        "Public deployments require DRIFTWATCH_CAPTURE_WORKER_URL and "
        "DRIFTWATCH_CAPTURE_WORKER_TOKEN. Set DRIFTWATCH_CAPTURE_ALLOW_IN_PROCESS=true "
        "only after accepting that Chromium will share the application's secrets boundary."
    )


def _default_page_capturer(settings: Settings) -> PageCapturer:
    if settings.capture_worker_url:
        return RemotePageCapturer(
            service_url=settings.capture_worker_url,
            token=settings.capture_worker_token.get_secret_value(),
            timeout_seconds=settings.capture_worker_client_timeout_seconds,
            max_request_bytes=settings.capture_worker_max_request_bytes,
            max_response_bytes=settings.capture_worker_max_response_bytes,
        )
    if not settings.is_local:
        logger.critical("Public deployment is using explicitly enabled in-process browser capture")
    return PlaywrightCapturer(
        timeout_seconds=settings.capture_timeout_seconds,
        settle_ms=settings.capture_settle_ms,
        user_agent=settings.capture_user_agent,
        channel=parse_channel(settings.capture_browser_channel),
        pin_dns=settings.capture_pin_dns,
        launch_timeout_seconds=settings.capture_launch_timeout_seconds,
        max_concurrent=settings.max_concurrent_captures,
    )


def create_app(
    settings: Settings | None = None,
    *,
    capturer: PageCapturer | None = None,
    analyzer: ChangeAnalyzer | None = None,
    channel: EmailChannel | None = None,
    picker: PickerService | None = None,
    billing_provider: BillingProvider | None = None,
    enable_scheduler: bool | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    if capturer is None:
        _require_capture_runtime(resolved)
    maintenance = MaintenanceMode()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(resolved.database_url)
        if resolved.run_migrations:
            await db.upgrade()  # build a fresh schema or migrate an existing one to head
        else:
            # A release pre-deploy command owns schema changes in this mode. Do
            # not fall back to ORM create_all(): model metadata cannot install
            # migration-only controls such as append-only ledger triggers.
            await db.require_migration_head()
        await seed_admin(db, resolved)

        page_capturer = capturer or _default_page_capturer(resolved)
        runner = SiteRunner(db, page_capturer, resolved, analyzer=analyzer, channel=channel)
        account_email_worker = AccountEmailWorker(db, resolved, channel=channel)
        scheduler = MonitorScheduler(
            db,
            runner,
            resolved,
            account_email_worker=account_email_worker,
        )
        picker_service = picker or PickerManager(
            enabled=resolved.picker_enabled and resolved.is_local,
            channel=parse_channel(resolved.picker_browser_channel),
            user_agent=resolved.capture_user_agent,
            session_timeout=resolved.picker_session_timeout_seconds,
            idle_timeout=resolved.picker_idle_timeout_seconds,
        )
        billing_service = billing_provider or build_billing_provider(resolved)

        app.state.settings = resolved
        app.state.db = db
        app.state.secret_box = SecretBox(*resolved.encryption_keys)
        app.state.runner = runner
        app.state.page_capturer = page_capturer
        app.state.scheduler = scheduler
        app.state.account_email_worker = account_email_worker
        app.state.maintenance = maintenance
        app.state.picker = picker_service
        app.state.login_throttle = LoginThrottle()
        app.state.billing_provider = billing_service

        should_start = resolved.scheduler_enabled if enable_scheduler is None else enable_scheduler
        if should_start:
            scheduler.start()
        try:
            yield
        finally:
            scheduler.shutdown()
            try:
                await picker_service.shutdown()
            finally:
                try:
                    if billing_provider is None:
                        await billing_service.aclose()
                finally:
                    try:
                        if capturer is None and isinstance(page_capturer, RemotePageCapturer):
                            await page_capturer.aclose()
                    finally:
                        await db.dispose()

    docs_url = "/docs" if resolved.expose_api_docs else None
    app = FastAPI(
        title="Driftwatch",
        version=__version__,
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url="/redoc" if resolved.expose_api_docs else None,
        openapi_url="/openapi.json" if resolved.expose_api_docs else None,
    )
    app.add_middleware(OriginGuard, settings=resolved)
    app.add_middleware(SecurityHeaders, hsts=not resolved.is_local)
    app.add_middleware(MaintenanceGate, mode=maintenance)
    app.add_middleware(RequestBodyLimit)
    # Added last so it wraps every user middleware, including origin rejections.
    app.add_middleware(RequestIdMiddleware)
    _register_exception_handlers(app)

    for module in (
        auth,
        branding,
        organizations,
        plans,
        billing,
        sites,
        projects,
        recipients,
        changes,
        notifications,
        operations,
        operators,
        picker_routes,
        settings_router,
        usage,
        exports,
        users,
        audit,
        support_access,
        admin,
        health,
    ):
        app.include_router(module.router)

    _mount_spa(app)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    async def handle_validation(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        errors = _redact_sensitive_inputs(exc.errors())
        return error_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=errors,
            error_code="validation_error",
        )

    async def handle_http(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        return error_response(
            request,
            status_code=exc.status_code,
            detail=exc.detail,
            error_code=http_error_code(exc.status_code),
            headers=exc.headers,
        )

    async def handle_domain(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, DriftwatchError)
        status_code, error_code = next(
            (
                contract
                for error_type, contract in _CONTRACT_BY_ERROR.items()
                if isinstance(exc, error_type)
            ),
            (400, "domain_error"),
        )
        return error_response(
            request,
            status_code=status_code,
            detail=str(exc),
            error_code=error_code,
        )

    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        request_id = request_id_for(request)
        logger.error(
            "Unhandled request error request_id=%s method=%s path=%s exception_type=%s",
            request_id,
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        return error_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            error_code="internal_server_error",
        )

    app.add_exception_handler(RequestValidationError, handle_validation)
    app.add_exception_handler(StarletteHTTPException, handle_http)
    for error_type in (*_CONTRACT_BY_ERROR, DriftwatchError):
        app.add_exception_handler(error_type, handle_domain)
    app.add_exception_handler(Exception, handle_unexpected)


def _redact_sensitive_inputs(value: object) -> object:
    """Scrub request values from validation errors before reflecting them.

    FastAPI includes the rejected input in a 422 response. That is useful for
    ordinary fields but would turn a malformed secret-bearing request into a
    plaintext API response.
    """
    if isinstance(value, list):
        return [_redact_sensitive_inputs(item) for item in value]
    if not isinstance(value, dict):
        return value
    is_fill = value.get("action") == "fill"
    redacted: dict[object, object] = {}
    for key, item in value.items():
        normalized = str(key).lower()
        sensitive = (
            normalized in {"password", "secret", "secret_value"}
            or normalized.endswith("_password")
            or normalized.endswith("_secret")
            or normalized.endswith("_api_key")
            or (is_fill and normalized == "value")
        )
        redacted[key] = "********" if sensitive else _redact_sensitive_inputs(item)
    return redacted


def _mount_spa(app: FastAPI) -> None:
    candidates = (PROJECT_ROOT / "web" / "dist", Path.cwd() / "web" / "dist")
    dist = next(
        (candidate.resolve() for candidate in candidates if (candidate / "index.html").is_file()),
        None,
    )
    if dist is None:
        logger.info("SPA bundle not found in %s; serving API only", candidates)
        return

    index = dist / "index.html"
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    dist_root = dist

    @app.get("/{spa_path:path}", include_in_schema=False)
    async def serve_spa(spa_path: str) -> FileResponse:
        # An unknown /api route must fail as a clean 404, not fall through to the
        # SPA shell: a renamed or deleted endpoint should break loudly, and an API
        # client deserves JSON, not a 200 page of HTML.
        if spa_path == "api" or spa_path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        if spa_path:
            candidate = (dist / spa_path).resolve()
            # Only serve real files that stay inside the build directory; a
            # crafted path must never escape it (path traversal).
            if candidate.is_file() and dist_root in candidate.parents:
                return FileResponse(candidate)
        return FileResponse(index)


def run() -> None:  # pragma: no cover - process entry point
    import os

    import uvicorn

    resolved = get_settings()
    configure_logging(resolved)
    # Platforms like Railway inject the port to bind via $PORT; honour it over the
    # configured default so the container is reachable without extra wiring.
    port = int(os.environ.get("PORT") or resolved.port)
    uvicorn.run(
        "driftwatch.app:create_app",
        factory=True,
        host=resolved.host,
        port=port,
        server_header=False,  # don't advertise the framework
        date_header=False,
        # Honor X-Forwarded-* only from a configured, trusted proxy so the client
        # IP (and thus the throttle key) is the real client, never spoofable.
        proxy_headers=resolved.forwarded_allow_ips is not None,
        forwarded_allow_ips=resolved.forwarded_allow_ips,
    )
