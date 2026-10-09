"""Webhook delivery: payload shape per format, SSRF refusal, and failure handling."""

from __future__ import annotations

import ipaddress
import json
from collections.abc import AsyncIterator

import httpx
import pytest

import driftwatch.security.urls as urls
from driftwatch.enums import NotificationStatus
from driftwatch.models import ChangeEvent, Site
from driftwatch.notifications.dispatch import _send_webhook
from driftwatch.notifications.webhook import WebhookError, WebhookEvent, send_webhook
from driftwatch.settings_store import WebhookConfig

EVENT = WebhookEvent(
    site_label="Acme",
    site_url="https://acme.example",
    headline="Price changed",
    summary="Now $9.99",
    significant=True,
    details_url="https://app.example/sites/1",
    detected_at="2026-06-18 10:00 UTC",
)


def _capturing_client(captured: dict[str, object], status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content)
        captured["headers"] = dict(request.headers)
        captured["extensions"] = dict(request.extensions)
        return httpx.Response(status)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_generic_payload() -> None:
    captured: dict[str, object] = {}
    async with _capturing_client(captured) as client:
        await send_webhook(EVENT, WebhookConfig(url="https://example.com/hook"), client=client)
    assert captured["url"] == "https://93.184.216.34/hook"
    assert captured["headers"]["host"] == "example.com"
    assert captured["headers"]["connection"] == "close"
    assert captured["extensions"]["sni_hostname"] == "example.com"
    body = captured["json"]
    assert body["event"] == "change_detected"
    assert body["headline"] == "Price changed"
    assert body["significant"] is True


async def test_forwards_stable_idempotency_key() -> None:
    captured: dict[str, object] = {}
    async with _capturing_client(captured) as client:
        await send_webhook(
            EVENT,
            WebhookConfig(url="https://example.com/hook"),
            idempotency_key="change:7:notification:v1:webhook:abc",
            client=client,
        )
    assert captured["headers"]["idempotency-key"] == ("change:7:notification:v1:webhook:abc")


async def test_slack_payload() -> None:
    captured: dict[str, object] = {}
    async with _capturing_client(captured) as client:
        await send_webhook(
            EVENT, WebhookConfig(url="https://example.com/hook", format="slack"), client=client
        )
    assert "text" in captured["json"]
    assert "Price changed" in captured["json"]["text"]


async def test_chat_text_renders_in_polish() -> None:
    captured: dict[str, object] = {}
    async with _capturing_client(captured) as client:
        await send_webhook(
            EVENT,
            WebhookConfig(url="https://example.com/hook", format="slack"),
            language="pl",
            client=client,
        )
    text = captured["json"]["text"]
    assert text.startswith("*Istotna zmiana*")


async def test_generic_payload_stays_language_neutral() -> None:
    # Machine-readable payloads carry raw values, not localized labels.
    captured: dict[str, object] = {}
    async with _capturing_client(captured) as client:
        await send_webhook(
            EVENT, WebhookConfig(url="https://example.com/hook"), language="pl", client=client
        )
    assert captured["json"]["significant"] is True
    assert "Istotna" not in str(captured["json"])


async def test_discord_payload() -> None:
    captured: dict[str, object] = {}
    async with _capturing_client(captured) as client:
        await send_webhook(
            EVENT, WebhookConfig(url="https://example.com/hook", format="discord"), client=client
        )
    assert "content" in captured["json"]


async def test_refuses_localhost_url() -> None:
    with pytest.raises(WebhookError):
        await send_webhook(EVENT, WebhookConfig(url="http://localhost/hook"))


async def test_refuses_private_ip() -> None:
    with pytest.raises(WebhookError) as raised:
        await send_webhook(EVENT, WebhookConfig(url="http://127.0.0.1/hook"))
    assert str(raised.value) == "webhook destination is not allowed"
    assert "127.0.0.1" not in str(raised.value)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com:not-a-port/hook",
        "https://127.000.000.001/hook",
        "https://example.com\n.invalid/hook",
    ],
)
async def test_refuses_urls_the_http_transport_cannot_parse(url: str) -> None:
    with pytest.raises(WebhookError, match="not allowed"):
        await send_webhook(EVENT, WebhookConfig(url=url))


async def test_refuses_hostname_with_any_non_public_dns_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def mixed_resolution(_: str) -> list[urls.IpAddress]:
        return [
            ipaddress.ip_address("93.184.216.34"),
            ipaddress.ip_address("169.254.169.254"),
        ]

    monkeypatch.setattr(urls, "_resolve", mixed_resolution)
    called = False

    def must_not_connect(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(must_not_connect)) as client:
        with pytest.raises(WebhookError, match="not allowed"):
            await send_webhook(
                EVENT,
                WebhookConfig(url="https://rebind.example/hook"),
                client=client,
            )

    assert called is False


async def test_dns_answer_is_pinned_without_a_second_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolutions = 0

    async def rebind_after_validation(_: str) -> list[urls.IpAddress]:
        nonlocal resolutions
        resolutions += 1
        answer = "93.184.216.34" if resolutions == 1 else "127.0.0.1"
        return [ipaddress.ip_address(answer)]

    monkeypatch.setattr(urls, "_resolve", rebind_after_validation)
    captured: dict[str, object] = {}
    async with _capturing_client(captured) as client:
        await send_webhook(
            EVENT,
            WebhookConfig(url="https://rebind.example:8443/hook"),
            client=client,
        )

    assert resolutions == 1
    assert captured["url"] == "https://93.184.216.34:8443/hook"
    assert captured["headers"]["host"] == "rebind.example:8443"
    assert captured["extensions"]["sni_hostname"] == "rebind.example"


async def test_public_ipv6_answer_is_pinned_with_original_tls_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ipv6_resolution(_: str) -> list[urls.IpAddress]:
        return [ipaddress.ip_address("2001:4860:4860::8888")]

    monkeypatch.setattr(urls, "_resolve", ipv6_resolution)
    captured: dict[str, object] = {}
    async with _capturing_client(captured) as client:
        await send_webhook(
            EVENT,
            WebhookConfig(url="https://ipv6.example/hook"),
            client=client,
        )

    assert captured["url"] == "https://[2001:4860:4860::8888]/hook"
    assert captured["headers"]["host"] == "ipv6.example"
    assert captured["extensions"]["sni_hostname"] == "ipv6.example"


async def test_webhook_redirect_is_not_followed_even_when_it_targets_private_ip() -> None:
    requested: list[str] = []

    def redirecting(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/internal"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(redirecting)) as client:
        with pytest.raises(WebhookError, match="returned 302"):
            await send_webhook(
                EVENT,
                WebhookConfig(url="https://example.com/hook"),
                client=client,
            )

    assert requested == ["https://93.184.216.34/hook"]


async def test_raises_on_error_status() -> None:
    captured: dict[str, object] = {}
    async with _capturing_client(captured, status=500) as client:
        with pytest.raises(WebhookError):
            await send_webhook(EVENT, WebhookConfig(url="https://example.com/hook"), client=client)


class _NeverReadResponse(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.read_attempted = False
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.read_attempted = True
        raise AssertionError("webhook response body must not be read")
        yield b"unreachable"  # pragma: no cover

    async def aclose(self) -> None:
        self.closed = True


async def test_error_response_is_closed_without_buffering_unreadable_large_body() -> None:
    stream = _NeverReadResponse()
    secret_url = "https://example.com/hooks/private-token"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            headers={"Content-Length": str(10**12)},
            stream=stream,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(WebhookError) as raised:
            await send_webhook(EVENT, WebhookConfig(url=secret_url), client=client)

    assert str(raised.value) == "webhook endpoint returned 503"
    assert "private-token" not in str(raised.value)
    assert stream.read_attempted is False
    assert stream.closed is True


async def test_transport_error_does_not_echo_secret_webhook_url() -> None:
    secret_url = "https://example.com/hooks/private-token"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed to connect to {request.url}", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(WebhookError) as raised:
            await send_webhook(EVENT, WebhookConfig(url=secret_url), client=client)

    assert str(raised.value) == "webhook delivery failed"
    assert "private-token" not in str(raised.value)


async def test_dispatch_logs_failed_webhook_without_leaking_url() -> None:
    # An unreachable/blocked URL is logged as a failed 'webhook' delivery, and the
    # log records the format label, never the secret URL.
    site = Site(url="https://acme.example", name="Acme")
    change = ChangeEvent(headline="x", summary="y", significant=True)
    log = await _send_webhook(
        change, site, WebhookConfig(url="http://127.0.0.1/secret-token", format="slack"), "u", "now"
    )
    assert log.status == NotificationStatus.FAILED
    assert log.channel == "webhook"
    assert log.recipient_email == "webhook:slack"
    assert "127.0.0.1" not in (log.recipient_email or "")
    assert log.error == "webhook delivery failed"
    assert "secret-token" not in (log.error or "")
