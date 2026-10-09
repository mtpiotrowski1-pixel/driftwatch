"""Settings: AI rules, OpenAI credentials, and email delivery.

Reading and writing settings is restricted to administrators because the values
include API keys and outbound mail configuration; secrets are returned masked.
The store is scoped to the caller: the operator edits the instance defaults,
while an org-admin reads the effective view of — and writes overrides for —
their own organization. ``/defaults`` exposes the inherited instance values so
the UI can show what a blank (inherited) field will use.
"""

from __future__ import annotations

import json
import math

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from driftwatch.api.deps import (
    AdminUser,
    LoginThrottleDep,
    SessionDep,
    SettingsDep,
    StoreDep,
    require_step_up,
)
from driftwatch.audit import record_audit_event
from driftwatch.enums import EmailChannelName
from driftwatch.models import Recipient, User
from driftwatch.monitoring.analyzer import response_schema
from driftwatch.monitoring.cleaner import (
    NON_CONTENT_TAGS,
    VOLATILE_ATTRIBUTES,
    volatile_value_patterns,
)
from driftwatch.monitoring.prompts import DEFAULT_BASE_PROMPT, DEFAULT_IMPORTANCE_RULES
from driftwatch.notifications.email import EmailEnvelope, SendError, default_sender_email
from driftwatch.notifications.webhook import WebhookError, WebhookEvent, send_webhook
from driftwatch.runner import build_channel
from driftwatch.schemas import (
    FactoryDefaultsOut,
    SettingsUpdate,
    TestEmailRequest,
    TestEmailResult,
    WebhookTestResult,
)
from driftwatch.security.throttle import LoginThrottle
from driftwatch.settings_store import INSTANCE_ONLY_KEYS, STEP_UP_SETTING_KEYS

router = APIRouter(prefix="/api/settings", tags=["settings"])

_MAX_TECHNICAL_ALERT_RECIPIENTS = 50


@router.get("/factory-defaults", response_model=FactoryDefaultsOut)
async def read_factory_defaults(_: AdminUser) -> FactoryDefaultsOut:
    """The built-in prompt defaults, the content the cleaner strips before a
    diff, and the model's fixed response shape — so the operator can see exactly
    what reaches the model and restore any customised value to these."""
    return FactoryDefaultsOut(
        base_prompt=DEFAULT_BASE_PROMPT,
        importance_rules=DEFAULT_IMPORTANCE_RULES,
        stripped_tags=sorted(NON_CONTENT_TAGS),
        volatile_attributes=sorted(VOLATILE_ATTRIBUTES),
        volatile_patterns=volatile_value_patterns(),
        response_fields=response_schema(),
    )


@router.get("", response_model=dict[str, str])
async def read_settings(store: StoreDep, _: AdminUser) -> dict[str, str]:
    return await store.public_values()


@router.get("/defaults", response_model=dict[str, str])
async def read_default_settings(store: StoreDep, _: AdminUser) -> dict[str, str]:
    return await store.defaults_values()


@router.put("", response_model=dict[str, str])
async def update_settings(
    payload: SettingsUpdate,
    request: Request,
    session: SessionDep,
    store: StoreDep,
    settings: SettingsDep,
    admin: AdminUser,
) -> dict[str, str]:
    values = _to_storage(payload)
    forbidden = sorted(values.keys() & INSTANCE_ONLY_KEYS) if store.is_org_scope else []
    if forbidden:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Instance-only settings cannot be changed in organization context: "
            + ", ".join(forbidden),
        )
    if "technical_alert_recipient_ids" in values:
        await _validate_technical_alert_recipient_ids(
            session,
            store.organization_id,
            payload.technical_alert_recipient_ids or [],
        )
    if values.keys() & STEP_UP_SETTING_KEYS:
        await require_step_up(request, admin, settings)
    await store.set_many(values)
    if values:
        record_audit_event(
            session,
            request,
            admin,
            action="settings.updated",
            target_type="settings",
            organization_id=store.organization_id,
            target_id=store.organization_id or "instance",
            details={"changed_keys": sorted(values)},
        )
    return await store.public_values()


@router.post("/test-email", response_model=TestEmailResult)
async def send_test_email(
    payload: TestEmailRequest,
    request: Request,
    session: SessionDep,
    store: StoreDep,
    settings: SettingsDep,
    admin: AdminUser,
    throttle: LoginThrottleDep,
) -> TestEmailResult:
    """Deliver one message through the currently configured channel so the
    operator can confirm credentials and sender before relying on alerts."""
    await _reserve_integration_test(request, admin, throttle, "email")
    if not admin.is_superadmin and payload.to.lower() != admin.email.lower():
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Organization administrators may send test email only to their own account",
        )

    config = await store.email(default_from=default_sender_email(settings.base_url))
    channel = build_channel(config)
    if not admin.is_superadmin:
        credential_key = {
            EmailChannelName.BREVO: "brevo_api_key",
            EmailChannelName.SMTP: "smtp_host",
        }.get(channel.name)
        if credential_key is not None and not await store.has_org_override(credential_key):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Configure organization-owned delivery credentials before sending a test",
            )
    envelope = EmailEnvelope(
        to=payload.to,
        subject="Driftwatch test email",
        html_body="<p>This is a test email from Driftwatch. "
        "Your email delivery is configured correctly.</p>",
        text_body="This is a test email from Driftwatch. "
        "Your email delivery is configured correctly.",
    )
    try:
        message_id = await channel.send(envelope)
    except SendError:
        record_audit_event(
            session,
            request,
            admin,
            action="settings.test_email",
            target_type="integration",
            organization_id=store.organization_id,
            target_label=str(payload.to),
            details={"channel": channel.name.value, "delivered": False},
        )
        # Provider exceptions can echo SMTP credentials, request payloads, or
        # the recipient address. The detailed cause belongs in redacted
        # observability, not in a browser-visible API response.
        return TestEmailResult(
            channel=channel.name.value,
            delivered=False,
            detail="Email delivery failed.",
        )
    record_audit_event(
        session,
        request,
        admin,
        action="settings.test_email",
        target_type="integration",
        organization_id=store.organization_id,
        target_label=str(payload.to),
        details={"channel": channel.name.value, "delivered": True},
    )
    return TestEmailResult(channel=channel.name.value, delivered=True, detail=message_id)


@router.post("/test-webhook", response_model=WebhookTestResult)
async def send_test_webhook(
    request: Request,
    session: SessionDep,
    store: StoreDep,
    settings: SettingsDep,
    admin: AdminUser,
    throttle: LoginThrottleDep,
) -> WebhookTestResult:
    """Post a sample event to the configured webhook so the operator can confirm
    the URL and format before relying on it."""
    await _reserve_integration_test(request, admin, throttle, "webhook")
    if not admin.is_superadmin and not await store.has_org_override("notification_webhook_url"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Configure an organization-owned webhook before sending a test",
        )
    config = await store.webhook()
    if config is None:
        record_audit_event(
            session,
            request,
            admin,
            action="settings.test_webhook",
            target_type="integration",
            organization_id=store.organization_id,
            details={"delivered": False, "reason": "not_configured"},
        )
        return WebhookTestResult(delivered=False, detail="No webhook URL is configured.")
    event = WebhookEvent(
        site_label="Driftwatch",
        site_url=settings.base_url,
        headline="Test webhook",
        summary="Your webhook is configured correctly.",
        significant=False,
        details_url=settings.base_url,
        detected_at="now",
    )
    try:
        await send_webhook(event, config)
    except WebhookError as exc:
        record_audit_event(
            session,
            request,
            admin,
            action="settings.test_webhook",
            target_type="integration",
            organization_id=store.organization_id,
            details={"delivered": False},
        )
        return WebhookTestResult(delivered=False, detail=str(exc))
    record_audit_event(
        session,
        request,
        admin,
        action="settings.test_webhook",
        target_type="integration",
        organization_id=store.organization_id,
        details={"delivered": True},
    )
    return WebhookTestResult(delivered=True, detail=None)


async def _validate_technical_alert_recipient_ids(
    session: SessionDep,
    organization_id: int | None,
    recipient_ids: list[int],
) -> None:
    if len(recipient_ids) > _MAX_TECHNICAL_ALERT_RECIPIENTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"At most {_MAX_TECHNICAL_ALERT_RECIPIENTS} technical alert recipients are allowed",
        )
    if any(recipient_id <= 0 for recipient_id in recipient_ids):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Technical alert recipient IDs must be positive integers",
        )
    if len(set(recipient_ids)) != len(recipient_ids):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Technical alert recipient IDs must be unique",
        )
    if not recipient_ids:
        return
    if organization_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Enter an organization before selecting technical alert recipients",
        )

    owned_ids = set(
        (
            await session.execute(
                select(Recipient.id).where(
                    Recipient.organization_id == organization_id,
                    Recipient.id.in_(recipient_ids),
                )
            )
        ).scalars()
    )
    if owned_ids != set(recipient_ids):
        # Do not distinguish a foreign recipient from a nonexistent one: that
        # would turn validation into a cross-tenant identifier oracle.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Every technical alert recipient must belong to the current organization",
        )


async def _reserve_integration_test(
    request: Request,
    admin: User,
    throttle: LoginThrottle,
    kind: str,
) -> None:
    client = request.client.host if request.client else "unknown"
    retry_after = await throttle.consume(
        f"settings-test:{kind}:user:{admin.id}:ip:{client}", max_actions=3
    )
    if retry_after is not None:
        seconds = math.ceil(retry_after)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many integration tests; try again later",
            headers={"Retry-After": str(seconds)},
        )


def _to_storage(payload: SettingsUpdate) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in payload.model_dump(exclude_unset=True, exclude={"clear_secret_keys"}).items():
        if value is None:
            continue
        if isinstance(value, list):
            values[key] = json.dumps(value)
        elif key == "default_notification_mode":
            values[key] = str(value.value if hasattr(value, "value") else value)
        elif isinstance(value, bool):
            values[key] = "true" if value else "false"
        else:
            values[key] = str(value)
    for key in payload.clear_secret_keys:
        values[key] = ""
    return values
