"""Regression tests for the metadata-only local email channel."""

from __future__ import annotations

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


def _stub_brevo(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[httpx.Response],
) -> list[dict[str, object]]:
    requests: list[dict[str, object]] = []

    class StubClient:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == 15.0

        async def __aenter__(self) -> StubClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            json: object,
            headers: dict[str, str],
        ) -> httpx.Response:
            requests.append({"url": url, "json": json, "headers": headers})
            return responses.pop(0)

    monkeypatch.setattr(httpx, "AsyncClient", StubClient)
    return requests


async def test_brevo_uses_stable_native_uuid_idempotency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _stub_brevo(
        monkeypatch,
        [
            httpx.Response(201, json={"messageId": "first"}),
            httpx.Response(201, json={"messageId": "second"}),
        ],
    )
    channel = BrevoChannel("api-secret", Sender("sender@example.com"))
    envelope = EmailEnvelope(
        to="person@example.com",
        subject="Account invitation",
        text_body="body",
        html_body="<p>body</p>",
        idempotency_key="account-email:12b34195-6ac3-4f27-9a6b-49526f80e70a",
    )

    assert await channel.send(envelope) == "first"
    assert await channel.send(envelope) == "second"

    payloads = [request["json"] for request in requests]
    assert all(isinstance(payload, dict) for payload in payloads)
    idempotency_values = [payload["headers"]["idempotencyKey"] for payload in payloads]
    assert idempotency_values[0] == idempotency_values[1]
    assert str(UUID(idempotency_values[0])) == idempotency_values[0]
    assert all("X-Driftwatch-Idempotency-Key" not in payload["headers"] for payload in payloads)


async def test_brevo_duplicate_acknowledgement_is_a_successful_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_brevo(
        monkeypatch,
        [httpx.Response(400, json={"code": "duplicate_parameter"})],
    )
    channel = BrevoChannel("api-secret", Sender("sender@example.com"))

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


async def test_brevo_error_does_not_echo_provider_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_brevo(
        monkeypatch,
        [
            httpx.Response(
                400,
                json={
                    "code": "invalid_parameter",
                    "message": "person@example.com sensitive-jwt",
                },
            )
        ],
    )
    channel = BrevoChannel("api-secret", Sender("sender@example.com"))

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
