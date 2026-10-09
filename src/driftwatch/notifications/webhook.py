"""Outbound webhook delivery for change notifications.

A webhook posts a change to a URL the operator controls — a generic JSON
endpoint, or a Slack / Discord incoming webhook with their expected payload
shape. The destination is run through the same public-URL guard the capturer
uses, so a configured URL cannot be turned into a server-side request forgery
against the host's own network, and redirects are not followed.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from driftwatch.exceptions import InvalidRequest
from driftwatch.localization import DEFAULT_LANGUAGE, tr
from driftwatch.security.outbound import PinnedHTTPEndpoint, resolve_pinned_http_endpoint
from driftwatch.settings_store import WebhookConfig

_TIMEOUT_SECONDS = 10.0


class WebhookError(Exception):
    """The webhook could not be delivered to its endpoint."""


@dataclass(frozen=True, slots=True)
class WebhookEvent:
    site_label: str
    site_url: str
    headline: str
    summary: str
    significant: bool
    details_url: str
    detected_at: str


async def send_webhook(
    event: WebhookEvent,
    config: WebhookConfig,
    *,
    language: str = DEFAULT_LANGUAGE,
    idempotency_key: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Deliver ``event`` to the configured webhook, raising ``WebhookError`` on a
    refused URL or a non-2xx response."""
    try:
        endpoint = await resolve_pinned_http_endpoint(config.url)
    except InvalidRequest as exc:
        raise WebhookError("webhook destination is not allowed") from exc

    payload = _payload(event, config.format, language)
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
    if client is not None:
        await _post(client, endpoint, payload, headers=headers)
        return
    async with httpx.AsyncClient(
        timeout=_TIMEOUT_SECONDS,
        follow_redirects=False,
        limits=httpx.Limits(max_keepalive_connections=0),
        trust_env=False,
    ) as owned:
        await _post(owned, endpoint, payload, headers=headers)


async def _post(
    client: httpx.AsyncClient,
    endpoint: PinnedHTTPEndpoint,
    payload: dict[str, object],
    *,
    headers: dict[str, str] | None = None,
) -> None:
    request = client.build_request("POST", endpoint.logical_url, json=payload, headers=headers)
    endpoint.pin(request)
    try:
        # The response body is irrelevant to delivery semantics and may be
        # attacker-controlled. Streaming lets us inspect the status without
        # buffering an unbounded (or deliberately unreadable) body in memory.
        response = await client.send(request, stream=True)
        try:
            status_code = response.status_code
        finally:
            await response.aclose()
    except httpx.HTTPError as exc:
        # httpx provider errors routinely include the complete request URL,
        # which for incoming webhooks often embeds a bearer token.
        raise WebhookError("webhook delivery failed") from exc
    if status_code >= 300:
        raise WebhookError(f"webhook endpoint returned {status_code}")


def _payload(event: WebhookEvent, fmt: str, language: str) -> dict[str, object]:
    # The generic JSON payload stays language-neutral (machine-readable keys and
    # raw values); only the human-facing chat formats are localized.
    if fmt == "slack":
        return {"text": _chat_text(event, language)}
    if fmt == "discord":
        return {"content": _chat_text(event, language)}
    return {
        "event": "change_detected",
        "site": event.site_label,
        "url": event.site_url,
        "headline": event.headline,
        "summary": event.summary,
        "significant": event.significant,
        "details_url": event.details_url,
        "detected_at": event.detected_at,
    }


def _chat_text(event: WebhookEvent, language: str) -> str:
    badge = tr(language, "badge.significant" if event.significant else "badge.change")
    lines = [f"*{badge}* — {event.headline or event.site_label}"]
    if event.summary:
        lines.append(event.summary)
    lines.append(event.details_url)
    return "\n".join(lines)
