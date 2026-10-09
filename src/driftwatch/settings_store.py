"""Typed access to runtime settings, layered per organization.

Operators change AI rules, the OpenAI key, and email delivery without a restart,
so these live in the database rather than the environment. Settings resolve in
two layers: an organization's own override (:class:`OrgSetting`) wins, otherwise
the instance default (:class:`Setting`) is inherited. A store with ``org_id`` set
reads and writes that organization's layer; ``org_id=None`` operates on the
instance defaults. Secret values are encrypted at rest with :class:`SecretBox`;
reads transparently decrypt and ``public_values`` masks them so they never leave
through the API.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.enums import EmailChannelName, NotificationMode
from driftwatch.localization import normalize_language
from driftwatch.models import OrgSetting, Setting
from driftwatch.security.crypto import SecretBox

SECRET_KEYS: frozenset[str] = frozenset(
    {"openai_api_key", "smtp_password", "brevo_api_key", "notification_webhook_url"}
)
# Changing these values can redirect privileged outbound traffic or replace a
# platform credential. A stolen admin session alone is therefore insufficient:
# the API requires a fresh step-up proof for every such mutation.
STEP_UP_SETTING_KEYS: frozenset[str] = SECRET_KEYS | frozenset(
    {
        "email_provider",
        "smtp_host",
        "smtp_port",
        "smtp_username",
        "smtp_security",
        "notification_from_email",
    }
)
# Settings that affect the shared engine or deployment, never an organization in
# isolation: an org cannot override them, so they always resolve to the instance
# default (the operator sets them once).
INSTANCE_ONLY_KEYS: frozenset[str] = frozenset(
    {
        "app_base_url",
        # Platform-owned AI credentials and cost accounting. A tenant consumes
        # the service through entitlements; BYOK needs an explicit product
        # contract rather than an implicit settings override.
        "openai_api_key",
        "openai_model",
        "openai_price_input_per_1m",
        "openai_price_cached_input_per_1m",
        "openai_price_output_per_1m",
        # Shared delivery infrastructure and sender identity. Tenant-specific
        # message copy, recipients and webhooks remain org-overridable.
        "email_provider",
        "smtp_host",
        "smtp_port",
        "smtp_username",
        "smtp_password",
        "smtp_security",
        "brevo_api_key",
        "notification_from_email",
        "capture_timeout_seconds",
        "capture_settle_ms",
        "capture_min_interval_seconds",
        "capture_jitter_ms",
        "snapshot_retention",
        # Scheduled backups copy the whole (shared) database file, so their
        # cadence and retention are the operator's alone.
        "backup_interval_hours",
        "backup_keep_count",
        # Plan-pricing knobs are platform-wide; an org never overrides them.
        "pricing_base_fee",
        "pricing_per_site_fee",
        "pricing_ai_margin",
        "pricing_unlimited_sites",
        "pricing_unlimited_checks",
        "pricing_currency",
        # Landing branding shapes the single public landing page, which has no
        # organization context, so only the operator sets it.
        "landing_tagline",
        "landing_hero_title",
        "landing_hero_subtitle",
        "landing_hero_background_url",
    }
)
# Branding keys served through the public (unauthenticated) /api/branding endpoint.
# The brand_* trio is also org-overridable (an org brands its own workspace); the
# landing_* keys are instance-only, set by the operator.
BRANDING_KEYS: tuple[str, ...] = (
    "brand_name",
    "brand_logo_url",
    "brand_accent_color",
    "landing_tagline",
    "landing_hero_title",
    "landing_hero_subtitle",
    "landing_hero_background_url",
)
# Operator-only knobs that must never surface through the general settings read,
# even to an org-admin: the pricing strategy is the operator's, exposed only
# through the superadmin-gated plans API.
_HIDDEN_FROM_READS: frozenset[str] = frozenset(
    {
        # Retired database override. BASE_URL is deployment-owned because it is
        # also the trusted origin for password-reset and invitation links.
        "app_base_url",
        "pricing_base_fee",
        "pricing_per_site_fee",
        "pricing_ai_margin",
        "pricing_unlimited_sites",
        "pricing_unlimited_checks",
        "pricing_currency",
    }
)
_MASK = "********"
# Stock product name, used wherever no brand_name has been configured.
DEFAULT_BRAND_NAME = "Driftwatch"


def _to_float(value: str | None) -> float:
    try:
        return float(value) if value else 0.0
    except ValueError:
        return 0.0


@dataclass(frozen=True, slots=True)
class OpenAIConfig:
    api_key: str
    model: str


@dataclass(frozen=True, slots=True)
class WebhookConfig:
    url: str
    format: str = "generic"  # generic | slack | discord


@dataclass(frozen=True, slots=True)
class EmailConfig:
    channel: EmailChannelName
    from_email: str
    from_name: str
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_security: str = "starttls"  # starttls | ssl | none
    brevo_api_key: str | None = None


class SettingsStore:
    def __init__(
        self, session: AsyncSession, secret_box: SecretBox, *, org_id: int | None = None
    ) -> None:
        self._session = session
        self._box = secret_box
        self._org_id = org_id

    @property
    def is_org_scope(self) -> bool:
        return self._org_id is not None

    @property
    def organization_id(self) -> int | None:
        """The tenant layer this store writes, or ``None`` for instance defaults."""
        return self._org_id

    async def get(self, key: str) -> str | None:
        row = await self._raw_row(key)
        if row is None:
            return None
        if key not in SECRET_KEYS:
            return row.value
        plaintext = self._box.decrypt(row.value)
        rotated = self._box.rotate(row.value)
        if plaintext is not None and rotated is not None and rotated != row.value:
            row.value = rotated
        return plaintext

    async def _raw_row(self, key: str) -> Setting | OrgSetting | None:
        """Resolve a key's stored value: the org override if any, else the
        instance default."""
        if self._org_id is not None and key not in INSTANCE_ONLY_KEYS:
            override = await self._override(key)
            if override is not None:
                return override
        return await self._session.get(Setting, key)

    async def _override(self, key: str) -> OrgSetting | None:
        rows = await self._session.execute(
            select(OrgSetting).where(
                OrgSetting.organization_id == self._org_id, OrgSetting.key == key
            )
        )
        return rows.scalar_one_or_none()

    async def has_org_override(self, key: str) -> bool:
        """Whether this tenant explicitly owns a value for ``key``.

        Security-sensitive test endpoints use this to prevent a tenant from
        exercising inherited platform credentials. Instance stores have no
        tenant layer and therefore return ``False``.
        """
        return self._org_id is not None and await self._override(key) is not None

    async def set_many(self, values: dict[str, str]) -> None:
        if self._org_id is None:
            await self._set_instance_defaults(values)
        else:
            await self._set_org_overrides(values)

    async def _set_instance_defaults(self, values: dict[str, str]) -> None:
        for key, value in values.items():
            if key in SECRET_KEYS and value == _MASK:
                continue  # masked round-trip: leave the stored secret untouched
            existing = await self._session.get(Setting, key)
            if key in SECRET_KEYS and value == "":
                if existing is not None:
                    await self._session.delete(existing)
                continue
            stored = self._box.encrypt(value) if key in SECRET_KEYS else value
            if existing is None:
                self._session.add(Setting(key=key, value=stored))
            else:
                existing.value = stored

    async def _set_org_overrides(self, values: dict[str, str]) -> None:
        for key, value in values.items():
            if key in INSTANCE_ONLY_KEYS:
                continue  # not overridable per organization
            if key in SECRET_KEYS and value == _MASK:
                continue  # masked round-trip: leave the stored override untouched
            existing = await self._override(key)
            if value == "":
                # Clearing a field reverts the organization to the instance default.
                if existing is not None:
                    await self._session.delete(existing)
                continue
            stored = self._box.encrypt(value) if key in SECRET_KEYS else value
            if existing is None:
                self._session.add(OrgSetting(organization_id=self._org_id, key=key, value=stored))
            else:
                existing.value = stored

    async def public_values(self) -> dict[str, str]:
        """Effective values for this store's scope (override else default), masked."""
        resolved = await self.defaults_values()
        if self._org_id is not None:
            overrides = (
                await self._session.execute(
                    select(OrgSetting).where(OrgSetting.organization_id == self._org_id)
                )
            ).scalars()
            for row in overrides:
                if row.key in INSTANCE_ONLY_KEYS:
                    continue
                resolved[row.key] = _MASK if row.key in SECRET_KEYS else row.value
        return resolved

    async def defaults_values(self) -> dict[str, str]:
        """The instance-default values, masked — what an org inherits when it has
        not overridden a key."""
        rows = (await self._session.execute(select(Setting))).scalars().all()
        hidden = _HIDDEN_FROM_READS | (INSTANCE_ONLY_KEYS if self._org_id is not None else set())
        return {
            row.key: (_MASK if row.key in SECRET_KEYS else row.value)
            for row in rows
            if row.key not in hidden
        }

    async def branding(self) -> dict[str, str]:
        """Resolve the public branding keys for this scope (org override else
        instance default), with unset keys blanked. None of these are secrets, so
        the values are returned verbatim."""
        return {key: (await self.get(key) or "") for key in BRANDING_KEYS}

    async def brand_name(self) -> str:
        """The white-label product name for this scope (org override else
        instance default), falling back to the stock name."""
        return await self.get("brand_name") or DEFAULT_BRAND_NAME

    async def importance_rules(self) -> str | None:
        return await self.get("importance_rules")

    async def base_prompt(self) -> str | None:
        return await self.get("base_prompt")

    async def ignore_selectors(self) -> list[str]:
        return await self._json_list("ignore_selectors", str)

    async def technical_alert_recipient_ids(self) -> list[int]:
        return await self._json_list("technical_alert_recipient_ids", int)

    async def email_subject_template(self) -> str | None:
        return await self.get("email_subject_template") or None

    async def webhook(self) -> WebhookConfig | None:
        url = await self.get("notification_webhook_url")
        if not url:
            return None
        fmt = (await self.get("notification_webhook_format") or "generic").lower()
        return WebhookConfig(
            url=url, format=fmt if fmt in ("generic", "slack", "discord") else "generic"
        )

    async def _json_list(self, key: str, cast: object) -> list:  # type: ignore[type-arg]
        raw = await self.get(key)
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        items = []
        for value in parsed:
            try:
                items.append(cast(value))  # type: ignore[operator]
            except (TypeError, ValueError):
                continue
        return items

    async def default_notification_mode(self) -> NotificationMode:
        raw = await self.get("default_notification_mode")
        try:
            return NotificationMode(raw) if raw else NotificationMode.ONLY_SIGNIFICANT
        except ValueError:
            return NotificationMode.ONLY_SIGNIFICANT

    async def openai(self, *, default_model: str, env_key: str = "") -> OpenAIConfig:
        return OpenAIConfig(
            api_key=(await self.get("openai_api_key") or env_key).strip(),
            model=await self.get("openai_model") or default_model,
        )

    async def email(self, *, default_from: str) -> EmailConfig:
        brevo = await self.get("brevo_api_key")
        smtp_host = await self.get("smtp_host")
        from_email = await self.get("notification_from_email") or default_from
        # An unset sender name follows the configured brand, so white-label
        # deployments do not sign their mail with the stock product name.
        from_name = await self.get("notification_from_name") or await self.brand_name()
        provider = (await self.get("email_provider") or "auto").lower()

        channel = self._resolve_channel(provider, brevo=bool(brevo), smtp=bool(smtp_host))
        security = (await self.get("smtp_security") or "starttls").lower()

        return EmailConfig(
            channel=channel,
            from_email=from_email,
            from_name=from_name,
            smtp_host=smtp_host,
            smtp_port=int(await self.get("smtp_port") or 587),
            smtp_username=await self.get("smtp_username"),
            smtp_password=await self.get("smtp_password"),
            smtp_security=security if security in ("starttls", "ssl", "none") else "starttls",
            brevo_api_key=brevo,
        )

    @staticmethod
    def _resolve_channel(provider: str, *, brevo: bool, smtp: bool) -> EmailChannelName:
        if provider == "brevo":
            return EmailChannelName.BREVO
        if provider == "smtp":
            return EmailChannelName.SMTP
        if provider == "log":
            return EmailChannelName.LOG
        # auto: pick by which credentials are configured.
        if brevo:
            return EmailChannelName.BREVO
        if smtp:
            return EmailChannelName.SMTP
        return EmailChannelName.LOG

    async def capture_pacing(self) -> tuple[float, float]:
        """Return ``(min_interval_seconds, jitter_seconds)`` between captures."""
        min_interval = _to_float(await self.get("capture_min_interval_seconds"))
        jitter_ms = _to_float(await self.get("capture_jitter_ms"))
        return min_interval, jitter_ms / 1000

    async def capture_timing(
        self, *, default_timeout_seconds: float, default_settle_ms: int
    ) -> tuple[float, int]:
        """Return ``(timeout_seconds, settle_ms)`` for a capture, DB over env."""
        timeout = await self.get("capture_timeout_seconds")
        settle = await self.get("capture_settle_ms")
        return (
            _to_float(timeout) if timeout else default_timeout_seconds,
            int(settle) if settle and settle.isdigit() else default_settle_ms,
        )

    async def snapshot_retention(self, *, default: int) -> int:
        raw = await self.get("snapshot_retention")
        return int(raw) if raw and raw.isdigit() else default

    async def backup_interval_hours(self, *, default: float) -> float:
        """Hours between scheduled database backups; 0 disables them."""
        raw = await self.get("backup_interval_hours")
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    async def backup_keep_count(self, *, default: int) -> int:
        """How many rotated backup files to keep."""
        raw = await self.get("backup_keep_count")
        return int(raw) if raw and raw.isdigit() else default

    async def watch_linked_documents(self) -> bool:
        """Opt-in: HEAD-probe linked documents (PDF/Word/Excel...) so a file
        replaced under the same URL is detected. Off by default."""
        raw = (await self.get("watch_linked_documents") or "").strip().lower()
        return raw in ("1", "true", "yes", "on")

    async def site_down_failure_threshold(self, *, default: int = 5) -> int:
        """How many consecutive capture failures escalate to a "site appears
        down" alert. Org-overridable; values below 1 fall back to the default."""
        raw = await self.get("site_down_failure_threshold")
        value = int(raw) if raw and raw.isdigit() else default
        return value if value >= 1 else default

    async def email_body_intro(self) -> str | None:
        return await self.get("email_body_intro") or None

    async def email_language(self) -> str:
        """Language of server-sent artifacts (emails, webhook chat text) for this
        scope: 'en' or 'pl', org-overridable, defaulting to English."""
        return normalize_language(await self.get("email_language"))
