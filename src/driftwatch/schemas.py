"""Pydantic request and response models — the typed edge of the HTTP API.

These are deliberately separate from the ORM models: the database shape and the
wire shape change for different reasons, and keeping them apart stops internal
columns from leaking into responses.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import date, datetime
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from driftwatch.enums import (
    AnalysisMode,
    AnalysisStatus,
    CheckJobKind,
    CheckJobSource,
    CheckJobStatus,
    NotificationMode,
    NotificationStatus,
    RetryStatus,
)

CheckStatusLiteral = Literal["baseline", "unchanged", "changed"]
PickerStateLiteral = Literal["starting", "waiting", "saved", "cancelled", "timed_out", "error"]
PricingCurrency = Literal["USD", "EUR", "GBP", "PLN"]
SecretSettingKey = Literal[
    "openai_api_key",
    "smtp_password",
    "brevo_api_key",
    "notification_webhook_url",
]

# Branding values are rendered into HTML attributes and CSS, so constrain them
# tightly. Each allows the empty string (which clears an org override): a hex
# colour. Brand images are accepted only by the validated same-origin upload
# endpoint, never as caller-provided URLs.
_HEX_OR_EMPTY = r"^(#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}))?$"


class _ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _PatchModel(BaseModel):
    """Omitted fields preserve values; explicit null only clears nullable fields."""

    _non_nullable_fields: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="before")
    @classmethod
    def _reject_nulls(cls, raw: object) -> object:
        if isinstance(raw, dict):
            invalid = [
                name for name in cls._non_nullable_fields if name in raw and raw[name] is None
            ]
            if invalid:
                raise ValueError(f"Fields cannot be null: {', '.join(invalid)}")
        return raw


# --- Organizations --------------------------------------------------------


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrganizationUpdate(_PatchModel):
    _non_nullable_fields = ("name", "is_active", "plan")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    # Plan and caps — operator-only. NULL caps clear a limit (unlimited).
    plan: str | None = Field(default=None, min_length=1, max_length=40)
    max_sites: int | None = Field(default=None, ge=0)
    max_members: int | None = Field(default=None, ge=0)
    monthly_ai_check_limit: int | None = Field(default=None, ge=0)
    # Assign a catalog plan: copies its caps onto the org. NULL detaches the plan
    # but leaves the current caps in place.
    plan_id: int | None = Field(default=None, ge=1)


class OrganizationOut(_ORMModel):
    id: int
    name: str
    is_active: bool
    plan: str = "free"
    plan_id: int | None = None
    max_sites: int | None = None
    max_members: int | None = None
    monthly_ai_check_limit: int | None = None
    created_at: datetime
    member_count: int = 0
    site_count: int = 0
    ai_checks_this_month: int = 0
    billing_managed: bool = False
    billing_suspended: bool = False


# --- Plans (subscription catalog) -----------------------------------------

_PLAN_KEY = r"^[a-z0-9][a-z0-9_-]*$"


class PlanBase(BaseModel):
    key: str = Field(min_length=1, max_length=40, pattern=_PLAN_KEY)
    name: str = Field(min_length=1, max_length=80)
    max_sites: int | None = Field(default=None, ge=0)
    max_members: int | None = Field(default=None, ge=0)
    monthly_ai_check_limit: int | None = Field(default=None, ge=0)
    # NULL = the price follows the algorithm; a value pins a fixed override.
    price_override_cents: int | None = Field(default=None, ge=0)
    currency: PricingCurrency = "USD"
    is_active: bool = True
    is_self_serve: bool = False
    sort_order: int = Field(default=0, ge=0)


class PlanCreate(PlanBase):
    pass


class PlanUpdate(_PatchModel):
    _non_nullable_fields = ("key", "name", "currency", "is_active", "is_self_serve", "sort_order")
    key: str | None = Field(default=None, min_length=1, max_length=40, pattern=_PLAN_KEY)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    max_sites: int | None = Field(default=None, ge=0)
    max_members: int | None = Field(default=None, ge=0)
    monthly_ai_check_limit: int | None = Field(default=None, ge=0)
    price_override_cents: int | None = Field(default=None, ge=0)
    currency: PricingCurrency | None = None
    is_active: bool | None = None
    is_self_serve: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)


class PlanOut(_ORMModel):
    id: int
    key: str
    name: str
    max_sites: int | None = None
    max_members: int | None = None
    monthly_ai_check_limit: int | None = None
    # The operator's pinned price, or NULL when the plan follows the algorithm.
    price_override_cents: int | None = None
    currency: str
    is_active: bool
    is_self_serve: bool = False
    sort_order: int
    # Computed by the API: the algorithm's price, and the one actually charged
    # (the override if set, else the algorithm's).
    suggested_price_cents: int = 0
    effective_price_cents: int = 0


class PricingContextOut(BaseModel):
    """The algorithm's tunable knobs and what it derived from real usage."""

    base_fee: float
    per_site_fee: float
    ai_margin: float
    unlimited_sites: int
    unlimited_checks: int
    currency: str
    model: str
    input_price_per_1m: float
    output_price_per_1m: float
    avg_prompt_tokens: int
    avg_completion_tokens: int
    cost_per_check: float


class PricingUpdate(BaseModel):
    # Upper bounds keep a stray knob (including +inf, which ge alone accepts) from
    # producing a price too large to round.
    base_fee: float | None = Field(default=None, ge=0, le=1_000_000)
    per_site_fee: float | None = Field(default=None, ge=0, le=1_000_000)
    ai_margin: float | None = Field(default=None, ge=0, le=100_000)
    unlimited_sites: int | None = Field(default=None, ge=1, le=10_000_000)
    unlimited_checks: int | None = Field(default=None, ge=1, le=100_000_000)
    currency: PricingCurrency | None = None


class PriceSuggestionOut(BaseModel):
    suggested_price_cents: int
    currency: str


class PublicPlanOut(BaseModel):
    """The public face of a plan for an unauthenticated pricing page: just the
    name, what's included, and the price actually charged — no operator knobs."""

    key: str
    name: str
    max_sites: int | None = None
    max_members: int | None = None
    monthly_ai_check_limit: int | None = None
    price_cents: int
    currency: str


# --- Auth -----------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AuthCapabilitiesOut(BaseModel):
    """Public authentication features enabled for this deployment."""

    registration_enabled: bool
    initial_setup_required: bool


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str | None = None
    # A company name spins up a new, isolated organization for this account.
    # plan_key remains accepted as non-entitling client intent for compatibility;
    # registration never copies catalog caps before verified payment activation.
    organization_name: str | None = Field(default=None, min_length=1, max_length=200)
    plan_key: str | None = Field(
        default=None,
        max_length=40,
        description=(
            "Accepted for compatibility only; public registration always receives "
            "the bounded free entitlement"
        ),
    )


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=1, max_length=2048)
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(_ORMModel):
    id: int
    email: EmailStr
    name: str | None
    is_admin: bool
    is_superadmin: bool = False
    organization_id: int | None = None
    totp_enabled: bool = False
    project_ids: list[int] = Field(default_factory=list)
    site_ids: list[int] = Field(default_factory=list)
    # Server-derived deployment policy. On a public deployment, every account
    # with administrative privileges is confined to TOTP enrollment until this
    # becomes false.
    mfa_enrollment_required: bool = False
    # An inactive tenant may still use the narrow billing recovery surface. The
    # client uses this server-derived state to avoid routing into APIs that are
    # intentionally locked while the organization is suspended.
    organization_suspended: bool = False
    # Only populated by /auth/me for an operator who entered a tenant. These
    # fields let the client display a server-validated context instead of
    # trusting its local header cache.
    acting_organization_id: int | None = None
    acting_organization_name: str | None = None


class LoginResult(BaseModel):
    """Either a completed login (``user`` set) or a TOTP challenge: the password
    was accepted and a second-factor code is now required."""

    totp_required: bool = False
    user: UserOut | None = None


class TotpLoginRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20)


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_uri: str
    qr_svg_data_uri: str


class TotpEnableRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20)


class TotpCodesOut(BaseModel):
    recovery_codes: list[str]


class TotpDisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class StepUpRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    totp_code: str | None = Field(default=None, max_length=20)


class SupportAccessRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=500)
    ticket: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("reason")
    @classmethod
    def _meaningful_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("reason must contain at least 10 non-whitespace characters")
        return value

    @field_validator("ticket")
    @classmethod
    def _clean_ticket(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("ticket cannot be blank")
        return value


class SupportAccessOut(BaseModel):
    required: bool
    access_enabled: bool
    organization_id: int
    expires_at: datetime | None = None


class OperationsDatabaseOut(BaseModel):
    backend: Literal["sqlite", "postgresql"]
    reachable: bool


class OperationsSchedulerOut(BaseModel):
    expected: bool
    running: bool
    stale: bool
    last_tick_at: datetime | None = None


class OperationsCaptureOut(BaseModel):
    mode: Literal["isolated_worker", "in_process", "injected"]
    status: Literal["ready", "unavailable", "not_probed"]
    active: int | None = None
    queued: int | None = None
    active_capacity: int | None = None
    queue_capacity: int | None = None


class OperationsCheckQueueOut(BaseModel):
    pending: int
    running: int
    dead: int
    oldest_pending_seconds: float | None = None
    capacity: int
    at_capacity: bool


class OperationsDeadCheckIncidentOut(BaseModel):
    """Operational metadata that intentionally excludes targets and diagnostics."""

    id: int
    organization_id: int
    site_id: int
    original_job_id: int | None = None
    kind: CheckJobKind
    source: CheckJobSource
    status: CheckJobStatus
    analyze: bool
    attempt_count: int
    enqueued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class OperationsDeadCheckIncidentPage(BaseModel):
    items: list[OperationsDeadCheckIncidentOut]
    next_before_id: int | None = None


class OperationsDeadCheckRedriveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(
        min_length=8,
        max_length=100,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    reason: str = Field(min_length=10, max_length=500)
    ticket: str = Field(min_length=1, max_length=100)

    @field_validator("reason")
    @classmethod
    def _meaningful_redrive_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("reason must contain at least 10 non-whitespace characters")
        return value

    @field_validator("ticket")
    @classmethod
    def _clean_redrive_ticket(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("ticket cannot be blank")
        return value


class OperationsDeadCheckRedriveOut(BaseModel):
    created: bool
    job: OperationsDeadCheckIncidentOut


class OperationsDeliveryQueueOut(BaseModel):
    pending: int
    failed: int
    sent: int
    exhausted: int
    leased: int
    oldest_unsent_seconds: float | None = None


class OperationsAccountEmailQueueOut(BaseModel):
    pending: int
    failed_total: int
    failed_recent: int
    sent: int
    cancelled: int
    leased: int
    oldest_pending_seconds: float | None = None
    stale_pending: bool
    pending_stale_after_seconds: int
    recent_failure_window_seconds: int


class OperationsBillingWebhooksOut(BaseModel):
    total: int
    received: int
    processing: int
    stale_processing: int
    completed: int
    failed: int
    stale_after_seconds: int
    last_processed_at: datetime | None = None
    last_failed_at: datetime | None = None


class OperationsStorageOut(BaseModel):
    db_bytes: int | None = None
    wal_bytes: int | None = None
    disk_free_bytes: int | None = None
    last_backup_at: datetime | None = None
    last_backup_file: str | None = None


class OperationsMaintenanceOut(BaseModel):
    enabled: bool
    active_requests: int


class OperationsOverviewOut(BaseModel):
    generated_at: datetime
    version: str
    status: Literal["ok", "degraded"]
    database: OperationsDatabaseOut
    scheduler: OperationsSchedulerOut
    capture: OperationsCaptureOut
    check_queue: OperationsCheckQueueOut
    delivery_queue: OperationsDeliveryQueueOut
    account_email_queue: OperationsAccountEmailQueueOut
    billing_webhooks: OperationsBillingWebhooksOut
    storage: OperationsStorageOut
    maintenance: OperationsMaintenanceOut


class UserDetail(UserOut):
    is_active: bool
    project_ids: list[int] = Field(default_factory=list)
    site_ids: list[int] = Field(default_factory=list)


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    name: str | None = None
    is_admin: bool = False


class UserUpdate(_PatchModel):
    _non_nullable_fields = ("email", "is_admin", "is_active")
    email: EmailStr | None = None
    name: str | None = None
    is_admin: bool | None = None
    is_active: bool | None = None


class OperatorOut(_ORMModel):
    id: int
    email: EmailStr
    name: str | None
    is_active: bool
    totp_enabled: bool
    created_at: datetime
    last_login_at: datetime | None = None


class OperatorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    name: str | None = Field(default=None, max_length=200)


class OperatorUpdate(_PatchModel):
    _non_nullable_fields = ("email", "is_active")
    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    name: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None


class AuditEventOut(_ORMModel):
    id: int
    occurred_at: datetime
    actor_user_id: int
    actor_email: EmailStr
    actor_is_superadmin: bool
    organization_id: int | None
    action: str
    target_type: str
    target_id: str | None
    target_label: str | None
    source_ip: str | None
    details: dict[str, object] = Field(default_factory=dict)


class PermissionsUpdate(BaseModel):
    project_ids: list[int] = Field(default_factory=list)
    site_ids: list[int] = Field(default_factory=list)


# --- Projects -------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    prompt: str | None = None
    notification_mode: NotificationMode | None = None
    recipient_ids: list[int] = Field(default_factory=list)


class ProjectUpdate(_PatchModel):
    _non_nullable_fields = ("name", "recipient_ids")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    prompt: str | None = None
    notification_mode: NotificationMode | None = None
    recipient_ids: list[int] | None = None


class ProjectOut(_ORMModel):
    id: int
    name: str
    prompt: str | None
    notification_mode: NotificationMode | None
    site_count: int = 0
    recipient_ids: list[int] = Field(default_factory=list)


# --- Sites ----------------------------------------------------------------


class InteractionStepIn(BaseModel):
    action: Literal["click", "fill", "wait_for", "wait"]
    selector: str | None = None
    secret_value: SecretStr | None = Field(
        default=None,
        json_schema_extra={"writeOnly": True},
    )
    secret_ref: UUID | None = None
    timeout_ms: int = Field(default=10_000, ge=0, le=120_000)

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_value(cls, raw: object) -> object:
        """Accept the old request shape without ever retaining ``value``.

        This compatibility path can be removed after deployed clients have
        moved to ``secret_value``. Legacy waits used ``value`` for milliseconds;
        legacy fills used it for the value that now goes straight to the vault.
        """
        if not isinstance(raw, dict) or "value" not in raw:
            return raw
        upgraded = dict(raw)
        value = upgraded.pop("value")
        if upgraded.get("action") == "fill" and "secret_value" not in upgraded:
            upgraded["secret_value"] = value
        elif upgraded.get("action") == "wait" and "timeout_ms" not in upgraded:
            with suppress(TypeError, ValueError):
                upgraded["timeout_ms"] = int(value)
        return upgraded

    @model_validator(mode="after")
    def _validate_shape(self) -> InteractionStepIn:
        if self.action != "wait" and not (self.selector or "").strip():
            raise ValueError(f"{self.action} interactions require a selector")
        if self.action == "fill":
            if (self.secret_value is None) == (self.secret_ref is None):
                raise ValueError(
                    "fill interactions require exactly one of secret_value or secret_ref"
                )
        elif self.secret_value is not None or self.secret_ref is not None:
            raise ValueError("only fill interactions may carry a secret")
        return self


class InteractionStepOut(BaseModel):
    action: Literal["click", "fill", "wait_for", "wait"]
    selector: str | None = None
    timeout_ms: int = 10_000
    secret_ref: UUID | None = None
    has_secret: bool = False

    @model_validator(mode="after")
    def _mark_secret(self) -> InteractionStepOut:
        self.has_secret = self.action == "fill" and self.secret_ref is not None
        return self


class SiteCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    name: str | None = Field(default=None, max_length=200)
    project_id: int | None = None
    css_selector: str | None = Field(default=None, max_length=500)
    prompt: str | None = None
    interaction_steps: list[InteractionStepIn] = Field(default_factory=list, max_length=20)
    ignore_selectors: list[str] = Field(default_factory=list)
    check_interval_minutes: int = Field(default=60, ge=1, le=10_080)
    enabled: bool = True
    notification_mode: NotificationMode | None = None
    analysis_mode: AnalysisMode = AnalysisMode.AI
    recipient_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_analysis_policy(self) -> SiteCreate:
        if (
            self.analysis_mode == AnalysisMode.DISABLED
            and self.notification_mode != NotificationMode.ALWAYS
        ):
            raise ValueError("Disabled AI requires notification_mode=always")
        return self


class SiteUpdate(_PatchModel):
    _non_nullable_fields = (
        "url",
        "interaction_steps",
        "ignore_selectors",
        "check_interval_minutes",
        "enabled",
        "recipient_ids",
        "analysis_mode",
    )
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    name: str | None = Field(default=None, max_length=200)
    project_id: int | None = None
    css_selector: str | None = Field(default=None, max_length=500)
    prompt: str | None = None
    interaction_steps: list[InteractionStepIn] | None = Field(default=None, max_length=20)
    ignore_selectors: list[str] | None = None
    check_interval_minutes: int | None = Field(default=None, ge=1, le=10_080)
    enabled: bool | None = None
    notification_mode: NotificationMode | None = None
    analysis_mode: AnalysisMode | None = None
    recipient_ids: list[int] | None = None


class SiteOut(_ORMModel):
    id: int
    url: str
    name: str | None
    project_id: int | None
    css_selector: str | None
    prompt: str | None
    interaction_steps: list[InteractionStepOut]
    ignore_selectors: list[str]
    check_interval_minutes: int
    enabled: bool
    notification_mode: NotificationMode | None
    analysis_mode: AnalysisMode
    last_checked_at: datetime | None
    last_alert_code: str | None
    last_alert_at: datetime | None
    # The underlying error message behind the alert badge (DNS vs timeout...).
    last_alert_detail: str | None
    consecutive_failure_count: int = 0
    created_at: datetime
    recipient_ids: list[int] = Field(default_factory=list)
    change_count: int = 0
    last_change_at: datetime | None = None


# --- Recipients -----------------------------------------------------------


class RecipientCreate(BaseModel):
    email: EmailStr
    name: str | None = None


class RecipientUpdate(_PatchModel):
    _non_nullable_fields = ("active",)
    name: str | None = None
    active: bool | None = None


class RecipientOut(_ORMModel):
    id: int
    email: EmailStr
    name: str | None
    active: bool


class SubstitutionCreate(BaseModel):
    substitute_email: EmailStr
    substitute_name: str | None = None
    start_date: date
    end_date: date
    # Optional scope: confine the cover to one project or one site. Both unset
    # (the default) means it covers all of the recipient's notifications.
    project_id: int | None = None
    site_id: int | None = None

    @model_validator(mode="after")
    def _check(self) -> SubstitutionCreate:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if self.project_id is not None and self.site_id is not None:
            raise ValueError("a substitution targets a project or a site, not both")
        return self


class SubstitutionOut(_ORMModel):
    id: int
    recipient_id: int
    substitute_email: EmailStr
    substitute_name: str | None
    start_date: str
    end_date: str
    project_id: int | None
    site_id: int | None


# --- Changes --------------------------------------------------------------


class ChangeOut(_ORMModel):
    id: int
    site_id: int
    created_at: datetime
    significant: bool | None
    headline: str | None
    summary: str | None
    ai_error: str | None
    ai_retry_count: int
    analysis_status: AnalysisStatus
    notification_error: str | None
    notification_retry_count: int
    retry_status: RetryStatus | None
    next_retry_at: datetime | None
    notified_at: datetime | None
    # The human review of the AI's significance verdict; None = not reviewed.
    user_verdict: bool | None = None
    user_verdict_at: datetime | None = None


class AnalysisRunOut(_ORMModel):
    """One entry of a change's analysis history, newest first."""

    id: int
    significant: bool
    headline: str
    summary: str
    created_at: datetime
    model: str | None = None
    rules_source: str | None = None
    rules_version: str | None = None
    system_prompt: str | None = None
    input_sha256: str | None = None
    input_truncated: bool | None = None
    usage_id: int | None = None


class ChangeDetail(ChangeOut):
    old_snapshot_id: int | None
    new_snapshot_id: int
    diff_text: str
    diff_html: str
    # Every successful analysis of this change, newest first — the head of the
    # list is the verdict currently shown on the change itself.
    analysis_runs: list[AnalysisRunOut] = Field(default_factory=list)


class VerdictUpdate(BaseModel):
    """Set or clear the human verdict on a change's significance. ``None``
    clears a previous review."""

    verdict: bool | None = None


class EffectiveRulesOut(BaseModel):
    """The importance rules the analyzer would actually apply at this level,
    with the inheritance level they come from: site | project | global | default."""

    source: str
    text: str


class AnalyzePreviewRequest(BaseModel):
    """Draft importance rules to dry-run against a past change's diff."""

    rules: str = Field(min_length=1, max_length=20_000)


class AnalyzePreviewOut(BaseModel):
    """The dry-run verdict. Nothing is persisted to the change itself."""

    significant: bool
    headline: str
    summary: str
    model: str
    cost_usd: float | None


class NotificationOut(_ORMModel):
    id: int
    change_id: int
    recipient_email: str
    channel: str
    status: NotificationStatus
    error: str | None
    message_id: str | None
    sent_at: datetime
    site_id: int | None = None
    site_name: str | None = None
    headline: str | None = None


# --- Runs -----------------------------------------------------------------


class RunResultOut(_ORMModel):
    site_id: int
    status: CheckStatusLiteral
    change_id: int | None = None
    significant: bool | None = None
    notified: bool = False
    recipients: int = 0
    ai_error: str | None = None
    capture_error: str | None = None


# --- Settings -------------------------------------------------------------


class FactoryDefaultsOut(BaseModel):
    """The built-in defaults and fixed pipeline behaviour, shown read-only so an
    operator can see what content is filtered before analysis, what the default
    prompts are, and the structured response the model must return."""

    base_prompt: str
    importance_rules: str
    stripped_tags: list[str]
    volatile_attributes: list[str]
    volatile_patterns: list[str]
    response_fields: dict[str, str]


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    importance_rules: str | None = None
    base_prompt: str | None = None
    default_notification_mode: NotificationMode | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    ignore_selectors: list[str] | None = None
    email_provider: str | None = Field(default=None, pattern="^(auto|brevo|smtp|log)$")
    smtp_host: str | None = None
    smtp_port: int | None = Field(default=None, ge=1, le=65_535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_security: str | None = Field(default=None, pattern="^(starttls|ssl|none)$")
    brevo_api_key: str | None = None
    notification_from_email: str | None = None
    notification_from_name: str | None = None
    email_subject_template: str | None = None
    email_body_intro: str | None = None
    # Empty string clears an organization's override back to the inherited value.
    email_language: str | None = Field(default=None, pattern="^(en|pl|)$")
    notification_webhook_url: str | None = None
    notification_webhook_format: str | None = Field(
        default=None, pattern="^(generic|slack|discord)$"
    )
    # Secret removal is explicit so an omitted or masked value can never erase a
    # credential accidentally. The endpoint applies the same step-up and audit
    # policy as it does when replacing a secret.
    clear_secret_keys: list[SecretSettingKey] = Field(default_factory=list, max_length=4)
    technical_alert_recipient_ids: list[int] | None = None
    # Consecutive failed captures before the stronger "site appears down"
    # alert fires. Org-overridable.
    site_down_failure_threshold: int | None = Field(default=None, ge=1, le=1000)
    # Opt-in probing of linked documents (PDF/Word/Excel...) for in-place
    # replacement under an unchanged URL. Org-overridable, off by default.
    watch_linked_documents: bool | None = None
    openai_price_input_per_1m: float | None = Field(default=None, ge=0)
    openai_price_cached_input_per_1m: float | None = Field(default=None, ge=0)
    openai_price_output_per_1m: float | None = Field(default=None, ge=0)
    capture_timeout_seconds: float | None = Field(default=None, ge=1, le=300)
    capture_settle_ms: int | None = Field(default=None, ge=0, le=30_000)
    capture_min_interval_seconds: float | None = Field(default=None, ge=0, le=60)
    capture_jitter_ms: int | None = Field(default=None, ge=0, le=10_000)
    snapshot_retention: int | None = Field(default=None, ge=1, le=10_000)
    # Branding. brand_* are org-overridable: an org-admin brands their own
    # workspace, while the operator's instance value is the default and drives the
    # public landing. landing_* are instance-only (there is one public landing).
    brand_name: str | None = Field(default=None, max_length=40)
    brand_accent_color: str | None = Field(default=None, pattern=_HEX_OR_EMPTY)
    landing_tagline: str | None = Field(default=None, max_length=120)
    landing_hero_title: str | None = Field(default=None, max_length=90)
    landing_hero_subtitle: str | None = Field(default=None, max_length=200)


class BrandingOut(BaseModel):
    """Public, unauthenticated branding for the marketing landing. Carries only
    the operator's instance-level values — never any other setting. Empty strings
    mean "unset", so the client falls back to its built-in defaults."""

    brand_name: str
    logo_url: str
    accent_color: str
    tagline: str
    hero_title: str
    hero_subtitle: str
    hero_background_url: str


class TestEmailRequest(BaseModel):
    to: EmailStr


class TestEmailResult(BaseModel):
    """Outcome of a test send: which channel was used and whether it delivered."""

    channel: str
    delivered: bool
    detail: str | None = None


class WebhookTestResult(BaseModel):
    delivered: bool
    detail: str | None = None


class RestoreResult(BaseModel):
    safety_copy: str


# --- Usage ----------------------------------------------------------------


class UsageByModel(BaseModel):
    model: str
    calls: int
    total_tokens: int
    cost_usd: float | None
    known_cost_usd: float = 0.0
    unknown_cost_calls: int = 0


class UsageBucket(BaseModel):
    label: str
    calls: int
    total_tokens: int
    cost_usd: float | None
    known_cost_usd: float = 0.0
    unknown_cost_calls: int = 0


# --- Visual picker --------------------------------------------------------


class PickerSessionCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    mode: str = Field(default="select", pattern="^(select|record)$")
    site_id: int | None = None


class PickerStatusOut(_ORMModel):
    session_id: str
    state: PickerStateLiteral
    mode: Literal["select", "record"]
    selector_count: int
    step_count: int
    channel: str | None
    detail: str | None


class PickerResultOut(BaseModel):
    css_selector: str
    selectors: list[str]
    steps: list[InteractionStepOut]


class PickerCapabilitiesOut(_ORMModel):
    available: bool
    reason: str | None


class UsageSummary(BaseModel):
    total_cost_usd: float | None
    known_cost_usd: float = 0.0
    unknown_cost_calls: int = 0
    total_tokens: int
    calls: int
    by_model: list[UsageByModel]
    by_month: list[UsageBucket] = Field(default_factory=list)
    by_site: list[UsageBucket] = Field(default_factory=list)
    by_project: list[UsageBucket] = Field(default_factory=list)


class VerdictAccuracyBucket(BaseModel):
    """How often humans agreed with the AI's significance verdict for one site.

    ``false_positives`` counts overrides of "significant" verdicts (the AI cried
    wolf); ``false_negatives`` counts overrides of "not significant" ones (the
    AI missed something that mattered)."""

    site_id: int
    label: str
    reviewed: int
    agreed: int
    false_positives: int
    false_negatives: int
    agreement_rate: float


class VerdictAccuracySummary(BaseModel):
    reviewed: int
    agreed: int
    false_positives: int
    false_negatives: int
    agreement_rate: float
    by_site: list[VerdictAccuracyBucket] = Field(default_factory=list)
