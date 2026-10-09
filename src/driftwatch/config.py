"""Application configuration, loaded from the environment or a local ``.env``.

A single :class:`Settings` instance is created at import time and shared through
:func:`get_settings`. Everything that needs configuration depends on this object
rather than reading ``os.environ`` directly.
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"

INSECURE_SECRET_KEY = "dev-insecure-change-me"
SUPPORTED_STRIPE_API_VERSION = "2025-06-30.basil"
_OFFICIAL_STRIPE_API_ORIGIN = "https://api.stripe.com"
# Publicly known values that must never sign a public deployment: the dev
# default above, and the .env.example placeholder — which is long enough to
# pass the length check, so an unedited `cp .env.example .env` would otherwise
# boot with a secret anyone can read off GitHub.
_KNOWN_INSECURE_SECRET_KEYS = frozenset({INSECURE_SECRET_KEY, "change-me-to-a-long-random-string"})
# Minimum secret length on a public deploy — 32 chars keeps the HMAC key from
# being short enough to brute-force, matching the JWT HS256 recommendation.
_MIN_SECRET_KEY_LENGTH = 32
# Loopback URL hosts. 0.0.0.0 / :: are bind-all (exposed), never "local browsing".
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _host_is_loopback(host: str) -> bool:
    h = (host or "").strip().lower()
    if h in {"localhost", "127.0.0.1", "::1"}:
        return True
    if h in {"", "0.0.0.0", "::"}:  # bind-all addresses expose all interfaces
        return False
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _normalize_http_origin(value: str, *, label: str) -> str:
    """Validate and canonicalize an HTTP(S) origin used as a trust boundary."""
    raw = value.strip()
    parts = urlsplit(raw)
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"{label} has an invalid port.") from exc
    hostname = (parts.hostname or "").lower()
    invalid = (
        parts.scheme not in {"http", "https"}
        or not hostname
        or hostname in {"0.0.0.0", "::"}
        or parts.username is not None
        or parts.password is not None
        or parts.path not in {"", "/"}
        or bool(parts.query)
        or bool(parts.fragment)
        or port == 0
        or any(character.isspace() or ord(character) < 32 for character in raw)
    )
    if invalid:
        raise ValueError(f"{label} must be an HTTP(S) origin without extra URL components.")
    loopback_origin = _host_is_loopback(hostname) or hostname.endswith(".localhost")
    if parts.scheme != "https" and not loopback_origin:
        raise ValueError(f"{label} must use HTTPS unless it is a loopback origin.")
    rendered_host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        rendered_host = f"{rendered_host}:{port}"
    return f"{parts.scheme}://{rendered_host}"


def _validate_https_document_url(value: str, *, label: str) -> str:
    """Validate a configured legal-document link without fetching its content."""
    raw = value.strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"{label} has an invalid port.") from exc
    if (
        len(raw) > 2_048
        or parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or port == 0
        or any(character.isspace() or ord(character) < 32 for character in raw)
    ):
        raise ValueError(f"{label} must be a public HTTPS document URL.")
    return raw


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DRIFTWATCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # HTTP server
    host: str = "127.0.0.1"
    port: int = 8000
    base_url: str = "http://localhost:8000"
    trusted_origins: list[str] = Field(default_factory=list)

    # Storage
    data_dir: Path = DEFAULT_DATA_DIR
    database_url: str = ""
    # Bring the schema to head with Alembic on startup. Disabled in the test
    # suite, which builds the schema directly from the models for speed.
    run_migrations: bool = True

    # Security. ``secret_key`` remains a local-development compatibility
    # fallback. Public deployments must explicitly separate session signing
    # from at-rest encryption; previous keys are comma-separated rotation rings.
    secret_key: str = INSECURE_SECRET_KEY
    session_secret_key: str = ""
    session_secret_key_previous: str = ""
    encryption_key: str = ""
    encryption_key_previous: str = ""
    session_ttl_hours: int = 24 * 14
    initial_admin_email: str | None = None
    initial_admin_password: str | None = None
    # None: permit the one-time claim only on a loopback source installation.
    # Compose explicitly opts in while its published port is bound to loopback.
    initial_admin_signup_enabled: bool | None = None
    public_registration_enabled: bool = False
    default_org_name: str = "Default organization"  # bootstrap tenant for the first account
    expose_api_docs: bool = False  # /docs, /redoc, /openapi.json — off by default
    # Trusted proxy hops for uvicorn's forwarded-headers handling. Set to the
    # proxy CIDR (or "*") only when behind a proxy you control, so the throttle
    # and client IP reflect the real client rather than the proxy.
    forwarded_allow_ips: str | None = None

    # Capture
    capture_timeout_seconds: float = 30.0
    capture_settle_ms: int = 750
    capture_user_agent: str = "Mozilla/5.0 (compatible; DriftwatchBot/1.0)"
    capture_browser_channel: str = "auto"  # auto | msedge | chrome | chromium
    capture_pin_dns: bool = True  # pin the browser to the vetted IP (anti DNS-rebind)
    capture_launch_timeout_seconds: float = 30.0  # bound browser launch/detection
    # Ceiling on browsers alive at once across the scheduler and on-demand "check
    # now"/snapshot calls, so a burst of manual checks can't spawn one Chromium per
    # request and exhaust host memory. Raise it on a larger box.
    max_concurrent_captures: int = 4
    # Public deployments use the browser-only worker as a secrets boundary. An
    # in-process browser remains available for loopback development and tests.
    capture_worker_url: str = ""
    capture_worker_token: SecretStr = SecretStr("")
    capture_worker_client_timeout_seconds: float = Field(default=100.0, ge=1.0, le=310.0)
    capture_worker_max_request_bytes: int = Field(default=65_536, ge=1_024, le=2_097_152)
    capture_worker_max_response_bytes: int = Field(default=8_388_608, ge=65_536, le=33_554_432)
    capture_worker_allow_insecure_http: bool = False
    capture_allow_in_process: bool = False

    # Visual selector picker (opens a real browser on the host; needs a display)
    picker_enabled: bool = True
    picker_browser_channel: str = "auto"
    picker_session_timeout_seconds: int = 300
    picker_idle_timeout_seconds: int = 120

    # Billing. Provider access can be configured for webhook reconciliation while
    # customer-facing checkout remains behind independent product/legal gates.
    billing_provider: str = "disabled"  # disabled | stripe
    billing_self_serve_enabled: bool = False
    billing_legal_gate_enabled: bool = False
    billing_terms_version: str = Field(default="", max_length=80)
    billing_privacy_version: str = Field(default="", max_length=80)
    billing_terms_url: str = Field(default="", max_length=2_048)
    billing_privacy_url: str = Field(default="", max_length=2_048)
    billing_terms_sha256: str = Field(default="", pattern=r"^(?:|[0-9a-f]{64})$")
    billing_privacy_sha256: str = Field(default="", pattern=r"^(?:|[0-9a-f]{64})$")
    billing_past_due_grace_days: int = Field(default=7, ge=0, le=90)
    billing_webhook_tolerance_seconds: int = Field(default=300, ge=30, le=900)
    billing_webhook_max_body_bytes: int = Field(default=524_288, ge=1_024, le=2_097_152)
    stripe_secret_key: SecretStr = SecretStr("")
    stripe_webhook_secret: SecretStr = SecretStr("")
    stripe_livemode: bool = False
    # Payload parsing is coupled to this exact Stripe schema version. A release
    # must update code and tests before changing the supported value.
    stripe_api_version: str = Field(default=SUPPORTED_STRIPE_API_VERSION, max_length=40)
    stripe_api_base_url: str = _OFFICIAL_STRIPE_API_ORIGIN
    stripe_timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)

    # AI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    max_diff_chars_for_ai: int = Field(default=16_000, ge=128, le=1_000_000)

    # Scheduling
    scheduler_enabled: bool = True
    scheduler_timezone: str = "UTC"
    scheduler_tick_seconds: int = 30
    max_checks_per_tick: int = 50
    snapshot_retention: int = 50
    per_site_budget_seconds: float = 120.0  # hard ceiling per site so one can't stall a tick
    ai_usage_retention_days: int = 180  # prune AI usage rows older than this
    check_queue_capacity: int = Field(default=1_000, ge=1, le=100_000)
    check_queue_per_org_capacity: int = Field(default=100, ge=1, le=10_000)
    check_job_lease_seconds: int = Field(default=180, ge=30, le=3_600)
    check_job_max_attempts: int = Field(default=5, ge=1, le=20)
    check_job_retention_days: int = Field(default=30, ge=1, le=365)
    account_email_job_retention_days: int = Field(default=30, ge=1, le=365)

    # Scheduled database backups (SQLite backend only; 0 hours disables them).
    backup_interval_hours: float = 24.0
    backup_keep_count: int = 7

    # Logging
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _derive_defaults(self) -> Settings:
        self.base_url = _normalize_http_origin(
            self.base_url,
            label="DRIFTWATCH_BASE_URL",
        )
        self.trusted_origins = list(
            dict.fromkeys(
                _normalize_http_origin(origin, label="DRIFTWATCH_TRUSTED_ORIGINS")
                for origin in self.trusted_origins
            )
        )
        self.billing_terms_url = _validate_https_document_url(
            self.billing_terms_url,
            label="DRIFTWATCH_BILLING_TERMS_URL",
        )
        self.billing_privacy_url = _validate_https_document_url(
            self.billing_privacy_url,
            label="DRIFTWATCH_BILLING_PRIVACY_URL",
        )
        if not self.database_url:
            self.database_url = f"sqlite+aiosqlite:///{self.data_dir / 'driftwatch.db'}"
        worker_url = self.capture_worker_url.strip().rstrip("/")
        worker_token = self.capture_worker_token.get_secret_value()
        if bool(worker_url) != bool(worker_token):
            raise ValueError(
                "DRIFTWATCH_CAPTURE_WORKER_URL and DRIFTWATCH_CAPTURE_WORKER_TOKEN "
                "must be configured together."
            )
        if worker_url:
            parsed = urlsplit(worker_url)
            try:
                parsed_port = parsed.port
            except ValueError as exc:
                raise ValueError("DRIFTWATCH_CAPTURE_WORKER_URL has an invalid port.") from exc
            invalid_url = (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or bool(parsed.query)
                or bool(parsed.fragment)
                or any(character.isspace() for character in worker_url)
                or parsed_port == 0
            )
            if invalid_url:
                raise ValueError(
                    "DRIFTWATCH_CAPTURE_WORKER_URL must be an HTTP(S) origin without "
                    "credentials, path, query, or fragment."
                )
            if parsed.scheme == "http" and not self.capture_worker_allow_insecure_http:
                raise ValueError(
                    "Plain HTTP to the capture worker requires the explicit "
                    "DRIFTWATCH_CAPTURE_WORKER_ALLOW_INSECURE_HTTP=true opt-in."
                )
            if len(worker_token) < _MIN_SECRET_KEY_LENGTH:
                raise ValueError(
                    "DRIFTWATCH_CAPTURE_WORKER_TOKEN must contain at least "
                    f"{_MIN_SECRET_KEY_LENGTH} characters."
                )
            if worker_token in {*self.token_secrets, *self.encryption_keys}:
                raise ValueError(
                    "DRIFTWATCH_CAPTURE_WORKER_TOKEN must be distinct from session and "
                    "encryption keys."
                )
            self.capture_worker_url = worker_url
        self.billing_provider = self.billing_provider.strip().lower()
        if self.billing_provider not in {"disabled", "stripe"}:
            raise ValueError("DRIFTWATCH_BILLING_PROVIDER must be 'disabled' or 'stripe'.")
        if self.billing_provider == "stripe":
            stripe_key = self.stripe_secret_key.get_secret_value()
            webhook_secret = self.stripe_webhook_secret.get_secret_value()
            missing = [
                name
                for name, value in (
                    ("DRIFTWATCH_STRIPE_SECRET_KEY", stripe_key),
                    ("DRIFTWATCH_STRIPE_WEBHOOK_SECRET", webhook_secret),
                    ("DRIFTWATCH_STRIPE_API_VERSION", self.stripe_api_version.strip()),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "Stripe billing configuration is incomplete: " + ", ".join(missing)
                )
            if len(stripe_key) < 16 or len(webhook_secret) < 16:
                raise ValueError(
                    "Stripe API and webhook secrets must contain at least 16 characters."
                )
            if self.stripe_livemode and not stripe_key.startswith("sk_live_"):
                raise ValueError("Stripe live mode requires a live secret API key (sk_live_).")
            if not self.stripe_livemode and not stripe_key.startswith("sk_test_"):
                raise ValueError("Stripe test mode requires an sk_test_ secret API key.")
            if not webhook_secret.startswith("whsec_"):
                raise ValueError("Stripe webhook secret must use the whsec_ prefix.")
            if stripe_key in {*self.token_secrets, *self.encryption_keys} or webhook_secret in {
                *self.token_secrets,
                *self.encryption_keys,
            }:
                raise ValueError("Stripe secrets must be distinct from application key material.")
            stripe_origin = _normalize_http_origin(
                self.stripe_api_base_url,
                label="DRIFTWATCH_STRIPE_API_BASE_URL",
            )
            if not stripe_origin.startswith("https://"):
                raise ValueError("DRIFTWATCH_STRIPE_API_BASE_URL must be an HTTPS origin.")
            if self.stripe_livemode and stripe_origin != _OFFICIAL_STRIPE_API_ORIGIN:
                raise ValueError(
                    "Stripe live mode requires the official https://api.stripe.com origin."
                )
            self.stripe_api_base_url = stripe_origin
            self.stripe_api_version = self.stripe_api_version.strip()
            if self.stripe_api_version != SUPPORTED_STRIPE_API_VERSION:
                raise ValueError(
                    "DRIFTWATCH_STRIPE_API_VERSION must exactly match the version supported "
                    f"by this release: {SUPPORTED_STRIPE_API_VERSION}."
                )
        elif self.billing_self_serve_enabled or self.billing_legal_gate_enabled:
            raise ValueError("Billing gates cannot be enabled while the provider is disabled.")
        if self.billing_self_serve_enabled:
            if self.public_registration_enabled:
                raise ValueError(
                    "Public registration and self-serve billing cannot be enabled together "
                    "until email ownership verification is implemented."
                )
            if not self.billing_legal_gate_enabled:
                raise ValueError("Self-serve billing requires the legal launch gate.")
            legal_evidence = (
                self.billing_terms_version.strip(),
                self.billing_privacy_version.strip(),
                self.billing_terms_url,
                self.billing_privacy_url,
                self.billing_terms_sha256,
                self.billing_privacy_sha256,
            )
            if not all(legal_evidence):
                raise ValueError(
                    "Self-serve billing requires versioned Terms and Privacy URLs with "
                    "approved SHA-256 digests."
                )
            self.billing_terms_version = self.billing_terms_version.strip()
            self.billing_privacy_version = self.billing_privacy_version.strip()
        # Session signing and at-rest encryption are separate trust domains. A
        # shared fallback is convenient for loopback development, but a public
        # deployment must configure both domains explicitly and keep their
        # complete rotation rings disjoint.
        if not self.is_local:
            missing_key_domains = [
                label
                for label, value in (
                    ("DRIFTWATCH_SESSION_SECRET_KEY", self.session_secret_key),
                    ("DRIFTWATCH_ENCRYPTION_KEY", self.encryption_key),
                )
                if not value
            ]
            if missing_key_domains:
                raise ValueError(
                    "Public deployments require explicit, distinct key material for: "
                    + ", ".join(missing_key_domains)
                )
            configured = {
                "DRIFTWATCH_SESSION_SECRET_KEY": self.token_secrets,
                "DRIFTWATCH_ENCRYPTION_KEY": self.encryption_keys,
            }
            for label, keys in configured.items():
                if any(
                    key in _KNOWN_INSECURE_SECRET_KEYS or len(key) < _MIN_SECRET_KEY_LENGTH
                    for key in keys
                ):
                    raise ValueError(
                        f"{label} and every configured previous key must be strong, unique "
                        f"values of at least {_MIN_SECRET_KEY_LENGTH} characters."
                    )
            if set(self.token_secrets) & set(self.encryption_keys):
                raise ValueError("Session-signing and encryption key rings must be fully distinct.")
        return self

    @property
    def token_secret(self) -> str:
        return self.session_secret_key or self.secret_key

    @property
    def token_secrets(self) -> tuple[str, ...]:
        return (self.token_secret, *_previous_keys(self.session_secret_key_previous))

    @property
    def encryption_keys(self) -> tuple[str, ...]:
        primary = self.encryption_key or self.secret_key
        return (primary, *_previous_keys(self.encryption_key_previous))

    @property
    def billing_provider_configured(self) -> bool:
        return self.billing_provider == "stripe"

    @property
    def billing_self_serve_ready(self) -> bool:
        return (
            self.billing_provider_configured
            and not self.public_registration_enabled
            and self.billing_self_serve_enabled
            and self.billing_legal_gate_enabled
            and bool(self.billing_terms_version)
            and bool(self.billing_privacy_version)
            and bool(self.billing_terms_url)
            and bool(self.billing_privacy_url)
            and bool(self.billing_terms_sha256)
            and bool(self.billing_privacy_sha256)
        )

    @property
    def initial_admin_signup_allowed(self) -> bool:
        if self.initial_admin_signup_enabled is not None:
            return self.initial_admin_signup_enabled
        return self.is_local

    @property
    def is_local(self) -> bool:
        """A safe local-only deployment: BOTH the public URL and the bind host are
        loopback. Any exposure — a public base_url, or a non-loopback bind such as
        0.0.0.0 — flips this off, enabling secret-key enforcement, Secure cookies,
        and HSTS. This prevents a forgotten localhost base_url behind a public bind
        from silently disabling all production hardening at once."""
        url_host = (urlsplit(self.base_url).hostname or "").lower()
        url_local = url_host in _LOCAL_HOSTS or url_host.endswith(".localhost")
        return url_local and _host_is_loopback(self.host)

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.scheduler_timezone)

    @property
    def log_file(self) -> Path:
        return self.data_dir / "driftwatch.log"

    def allowed_origins(self) -> set[str]:
        """Origins accepted for state-changing requests (CSRF defence)."""
        origins = {self.base_url.rstrip("/"), *(o.rstrip("/") for o in self.trusted_origins)}
        return {o for o in origins if o}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings


def _previous_keys(value: str) -> tuple[str, ...]:
    return tuple(key.strip() for key in value.split(",") if key.strip())
