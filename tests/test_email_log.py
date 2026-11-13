"""Log and Brevo email channels: metadata-only logging, idempotency, safe errors."""

from __future__ import annotations

import json
import logging
from uuid import UUID

import httpx
import pytest

from driftwatch.notifications.email import (
    BrevoChannel,
    EmailEnvelope,
    LogChannel,
    Sender,
    SendError,
)


async def test_log_channel_never_logs_message_content_or_full_recipient(caplog) -> None:
    envelope = EmailEnvelope(
        to="person@example.com",
        subject="Reset your password",
        text_body="Secret reset URL: https://app.test/reset#token=sensitive-jwt",
        html_body="<p>sensitive-jwt</p>",
    )

    with caplog.at_level(logging.INFO, logger="driftwatch.notifications.email"):
        assert await LogChannel().send(envelope) == "logged"

    rendered = caplog.text
    assert "recipient_domain=example.com" in rendered
    assert "person@example.com" not in rendered
    assert "sensitive-jwt" not in rendered
    assert "Reset your password" not in rendered


def _brevo(responses: list[httpx.Response]) -> tuple[BrevoChannel, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return responses.pop(0)

    channel = BrevoChannel(
        "api-secret", Sender("sender@example.com"), transport=httpx.MockTransport(handler)
    )
    return channel, requests


async def test_brevo_uses_stable_native_uuid_idempotency() -> None:
    channel, requests = _brevo(
        [
            httpx.Response(201, json={"messageId": "first"}),
            httpx.Response(201, json={"messageId": "second"}),
        ]
    )
    envelope = EmailEnvelope(
        to="person@example.com",
        subject="Account invitation",
        text_body="body",
        html_body="<p>body</p>",
        idempotency_key="account-email:12b34195-6ac3-4f27-9a6b-49526f80e70a",
    )

    assert await channel.send(envelope) == "first"
    assert await channel.send(envelope) == "second"

    payloads = [json.loads(request.content) for request in requests]
    assert all(isinstance(payload, dict) for payload in payloads)
    idempotency_values = [payload["headers"]["idempotencyKey"] for payload in payloads]
    assert idempotency_values[0] == idempotency_values[1]
    assert str(UUID(idempotency_values[0])) == idempotency_values[0]
    assert all("X-Driftwatch-Idempotency-Key" not in payload["headers"] for payload in payloads)


async def test_brevo_duplicate_acknowledgement_is_a_successful_handoff() -> None:
    channel, _ = _brevo([httpx.Response(400, json={"code": "duplicate_parameter"})])

    result = await channel.send(
        EmailEnvelope(
            to="person@example.com",
            subject="Account invitation",
            text_body="body",
            html_body="<p>body</p>",
            idempotency_key="stable-logical-delivery",
        )
    )

    assert result == "brevo-idempotent-duplicate"


async def test_brevo_error_does_not_echo_provider_response() -> None:
    channel, _ = _brevo(
        [
            httpx.Response(
                400,
                json={
                    "code": "invalid_parameter",
                    "message": "person@example.com sensitive-jwt",
                },
            )
        ]
    )

    with pytest.raises(SendError) as caught:
        await channel.send(
            EmailEnvelope(
                to="person@example.com",
                subject="Password reset",
                text_body="sensitive-jwt",
                html_body="<p>sensitive-jwt</p>",
            )
        )

    assert "HTTP 400" in str(caught.value)
    assert "person@example.com" not in str(caught.value)
    assert "sensitive-jwt" not in str(caught.value)


async def test_brevo_network_failure_is_a_send_error_without_request_details() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out posting with api-key api-secret", request=request)

    channel = BrevoChannel(
        "api-secret", Sender("sender@example.com"), transport=httpx.MockTransport(refuse)
    )

    with pytest.raises(SendError) as caught:
        await channel.send(
            EmailEnvelope(to="person@example.com", subject="s", text_body="b", html_body="<p>b</p>")
        )

    assert str(caught.value) == "brevo request failed"
