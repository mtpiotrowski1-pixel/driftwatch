"""Resolve notification targets and enqueue their durable delivery intents.

Recipients come from the site directly and from its project; the two sets are
merged and de-duplicated by email. Every attempt — sent, failed, or skipped —
is written to the audit log. The complete target set is committed before any
provider call, and the change is marked notified only after every required
destination has reached the sent state.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.enums import NotificationStatus
from driftwatch.localization import DEFAULT_LANGUAGE
from driftwatch.models import (
    ChangeEvent,
    NotificationLog,
    Recipient,
    RecipientSubstitution,
    Site,
    project_recipients,
    site_recipients,
)
from driftwatch.notifications.email import EmailChannel, EmailEnvelope, SendError
from driftwatch.notifications.outbox import (
    DeliverySpec,
    destination_key,
    dispatch_notification,
    enqueue_notification,
)
from driftwatch.notifications.render import RenderedEmail, render_change_email
from driftwatch.notifications.webhook import WebhookError, WebhookEvent, send_webhook
from driftwatch.security.crypto import SecretBox
from driftwatch.settings_store import WebhookConfig

# Audit-log reason recorded when a change had nobody to deliver to.
SKIPPED_NO_RECIPIENTS = "no recipients resolved for this site or its project"


def skipped_delivery_log(change_id: int) -> NotificationLog:
    """An audit row recording that delivery was skipped for lack of recipients,
    so the change surfaces under the notifications feed's "skipped" filter
    instead of vanishing silently."""
    return NotificationLog(
        change_id=change_id,
        recipient_email="—",
        channel="none",
        status=NotificationStatus.SKIPPED,
        error=SKIPPED_NO_RECIPIENTS,
    )


async def dispatch_change(
    session: AsyncSession,
    change: ChangeEvent,
    site: Site,
    *,
    channel: EmailChannel,
    app_base_url: str,
    subject_template: str | None = None,
    intro: str | None = None,
    webhook: WebhookConfig | None = None,
    today: date | None = None,
    language: str = DEFAULT_LANGUAGE,
    secret_box: SecretBox | None = None,
    force: bool = False,
) -> list[NotificationLog]:
    recipients = await resolve_recipients(session, site)
    if not recipients and webhook is None:
        _, created = await enqueue_notification(session, change, [])
        if created:
            session.add(skipped_delivery_log(change.id))
        await session.commit()
        return []

    # Deep-link to the exact change so the recipient lands on what was emailed,
    # not merely the site's newest change.
    details_url = f"{app_base_url.rstrip('/')}/sites/{site.id}?change={change.id}"
    detected_at = change.created_at.strftime("%Y-%m-%d %H:%M UTC")
    email = render_change_email(
        site_label=site.name or site.url,
        site_url=site.url,
        headline=change.headline or "",
        summary=change.summary or "",
        significant=bool(change.significant),
        details_url=details_url,
        detected_at=detected_at,
        subject_template=subject_template,
        intro=intro,
        language=language,
    )

    specs: list[DeliverySpec] = []
    if recipients:
        targets = await resolve_send_targets(
            session, recipients, today or datetime.now(UTC).date(), site
        )
        for to_email, to_name in targets:
            specs.append(
                DeliverySpec(
                    kind="email",
                    destination_key=destination_key("email", to_email.casefold()),
                    destination_label=to_email,
                    payload={
                        "to": to_email,
                        "to_name": to_name,
                        "subject": email.subject,
                        "html_body": email.html_body,
                        "text_body": email.text_body,
                    },
                )
            )

    if webhook is not None:
        if secret_box is None:
            raise ValueError("A secret box is required to persist a webhook destination")
        specs.append(
            DeliverySpec(
                kind="webhook",
                destination_key=destination_key("webhook", f"{webhook.format}:{webhook.url}"),
                destination_label=f"webhook:{webhook.format}",
                payload={
                    "site_label": site.name or site.url,
                    "site_url": site.url,
                    "headline": change.headline or "",
                    "summary": change.summary or "",
                    "significant": bool(change.significant),
                    "details_url": details_url,
                    "detected_at": detected_at,
                    "language": language,
                },
                target_ciphertext=secret_box.encrypt(
                    json.dumps({"url": webhook.url, "format": webhook.format})
                ),
            )
        )

    outbox, _ = await enqueue_notification(session, change, specs)
    # No provider is called before the outbox and complete target set are durable.
    await session.commit()
    return await dispatch_notification(
        session,
        outbox.id,
        channel=channel,
        secret_box=secret_box,
        force=force,
    )


async def _send_webhook(
    change: ChangeEvent,
    site: Site,
    webhook: WebhookConfig,
    details_url: str,
    detected_at: str,
    language: str = DEFAULT_LANGUAGE,
) -> NotificationLog:
    # The endpoint label, never the URL: the configured URL is a secret (e.g. a
    # Slack token) and must not land in the audit log.
    label = f"webhook:{webhook.format}"
    event = WebhookEvent(
        site_label=site.name or site.url,
        site_url=site.url,
        headline=change.headline or "",
        summary=change.summary or "",
        significant=bool(change.significant),
        details_url=details_url,
        detected_at=detected_at,
    )
    try:
        await send_webhook(event, webhook, language=language)
    except WebhookError:
        return NotificationLog(
            change_id=change.id,
            recipient_email=label,
            channel="webhook",
            status=NotificationStatus.FAILED,
            error="webhook delivery failed",
        )
    return NotificationLog(
        change_id=change.id,
        recipient_email=label,
        channel="webhook",
        status=NotificationStatus.SENT,
    )


async def resolve_recipients(session: AsyncSession, site: Site) -> list[Recipient]:
    direct = (
        select(Recipient)
        .join(site_recipients, Recipient.id == site_recipients.c.recipient_id)
        .where(site_recipients.c.site_id == site.id)
    )
    queries = [direct]
    if site.project_id is not None:
        inherited = (
            select(Recipient)
            .join(project_recipients, Recipient.id == project_recipients.c.recipient_id)
            .where(project_recipients.c.project_id == site.project_id)
        )
        queries.append(inherited)

    by_email: dict[str, Recipient] = {}
    for query in queries:
        for recipient in (await session.execute(query)).scalars():
            if recipient.active:
                by_email.setdefault(recipient.email, recipient)
    return list(by_email.values())


async def resolve_send_targets(
    session: AsyncSession, recipients: list[Recipient], today: date, site: Site
) -> list[tuple[str, str | None]]:
    """Map recipients to ``(email, name)`` targets, applying active substitutions.

    A recipient who is away on ``today`` has their mail redirected to the
    stand-in — but only by a cover that applies to ``site`` (an unscoped cover, or
    one scoped to this site or its project). Targets are de-duplicated by email so
    a shared stand-in is mailed once.
    """
    substitutes = await _active_substitutes(
        session, [r.id for r in recipients], today.isoformat(), site
    )

    targets: dict[str, str | None] = {}
    for recipient in recipients:
        email, name = substitutes.get(recipient.id, (recipient.email, recipient.name))
        targets.setdefault(email, name)
    return list(targets.items())


def _scope_rank(substitution: RecipientSubstitution, site: Site) -> int | None:
    """How specifically a cover applies to ``site``: site match (2) beats project
    match (1) beats unscoped (0). ``None`` means it does not apply here."""
    if substitution.site_id is not None:
        return 2 if substitution.site_id == site.id else None
    if substitution.project_id is not None:
        return 1 if substitution.project_id == site.project_id else None
    return 0


async def _active_substitutes(
    session: AsyncSession, recipient_ids: list[int], today_iso: str, site: Site
) -> dict[int, tuple[str, str | None]]:
    if not recipient_ids:
        return {}
    rows = await session.execute(
        select(RecipientSubstitution)
        .where(
            RecipientSubstitution.recipient_id.in_(recipient_ids),
            RecipientSubstitution.start_date <= today_iso,
            RecipientSubstitution.end_date >= today_iso,
        )
        .order_by(RecipientSubstitution.id)
    )
    # For each recipient keep the most specific applicable cover; the id order
    # breaks ties between covers of equal specificity in favour of the earliest.
    best: dict[int, tuple[int, tuple[str, str | None]]] = {}
    for substitution in rows.scalars():
        rank = _scope_rank(substitution, site)
        if rank is None:
            continue
        current = best.get(substitution.recipient_id)
        if current is None or rank > current[0]:
            best[substitution.recipient_id] = (
                rank,
                (substitution.substitute_email, substitution.substitute_name),
            )
    return {recipient_id: target for recipient_id, (_, target) in best.items()}


async def send_site_alert(
    channel: EmailChannel, email: RenderedEmail, recipients: list[str]
) -> int:
    """Best-effort delivery of an operational alert; returns the count sent."""
    sent = 0
    for address in recipients:
        envelope = EmailEnvelope(
            to=address,
            subject=email.subject,
            html_body=email.html_body,
            text_body=email.text_body,
        )
        try:
            await channel.send(envelope)
            sent += 1
        except SendError:
            continue
    return sent
