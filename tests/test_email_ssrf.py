"""The SMTP channel is an SSRF sink: its host is tenant-supplied. It must refuse
a server that resolves to a non-public address before connecting, so the
test-email endpoint cannot be turned into an internal port/reachability probe."""

from __future__ import annotations

import asyncio
import ipaddress
import socket

import aiosmtplib
import httpx
import pytest

import driftwatch.notifications.email as email_module
import driftwatch.security.urls as urls
from driftwatch.notifications.email import EmailEnvelope, Sender, SendError, SMTPChannel, SMTPConfig

_ENVELOPE = EmailEnvelope(
    to="ops@example.com",
    subject="probe",
    html_body="<p>probe</p>",
    text_body="probe",
)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",  # loopback
        "10.0.0.5",  # RFC1918 private
        "169.254.169.254",  # cloud metadata / link-local
        "100.64.0.1",  # CGNAT shared space
        "::1",  # IPv6 loopback
        "fd00::1",  # IPv6 unique-local
        "fe80::1",  # IPv6 link-local
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "2002:0a00:0001::",  # 6to4 carrying RFC1918 IPv4
        "64:ff9b::a00:1",  # NAT64 carrying RFC1918 IPv4
        "localhost",
        "broker.internal",
        "smtp.example.com\n.invalid",
    ],
)
async def test_smtp_refuses_non_public_host(host: str) -> None:
    channel = SMTPChannel(SMTPConfig(host=host), Sender(email="from@example.com"))

    with pytest.raises(SendError, match="non-public"):
        await channel.send(_ENVELOPE)


async def test_smtp_allows_a_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    # A legitimate public mail host passes the guard and reaches the transport.
    # (The DNS stub resolves the name to a public IP; the transport is faked so
    # the suite stays offline.)
    sent: dict[str, object] = {}
    connected: dict[str, object] = {}

    class SocketDouble:
        closed = False

        def close(self) -> None:
            self.closed = True

    sock = SocketDouble()

    async def fake_connect(addresses: list[str], port: int, timeout_seconds: float) -> SocketDouble:
        connected.update(addresses=addresses, port=port, timeout=timeout_seconds)
        return sock

    async def fake_send(message: object, **kwargs: object) -> tuple[dict[str, object], str]:
        sent.update(kwargs)
        return {}, "ok"

    monkeypatch.setattr(email_module, "_connect_vetted_socket", fake_connect)
    monkeypatch.setattr(aiosmtplib, "send", fake_send)
    channel = SMTPChannel(SMTPConfig(host="smtp.example.com", port=587), Sender(email="x@y.com"))

    await channel.send(_ENVELOPE)

    assert connected == {
        "addresses": ["93.184.216.34"],
        "port": 587,
        "timeout": 15.0,
    }
    assert sent["hostname"] == "smtp.example.com"
    assert sent["sock"] is sock
    assert "port" not in sent
    assert sent["start_tls"] is True
    assert sent["use_tls"] is False
    assert sent["validate_certs"] is True
    # The real aiosmtplib transport assumes ownership and closes on normal exit.
    assert sock.closed is False


async def test_smtp_closes_pinned_socket_when_provider_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SocketDouble:
        closed = False

        def close(self) -> None:
            self.closed = True

    sock = SocketDouble()

    async def fake_connect(_: list[str], __: int, ___: float) -> SocketDouble:
        return sock

    async def failing_send(_: object, **__: object) -> tuple[dict[str, object], str]:
        raise aiosmtplib.SMTPException("setup failed")

    monkeypatch.setattr(email_module, "_connect_vetted_socket", fake_connect)
    monkeypatch.setattr(aiosmtplib, "send", failing_send)
    channel = SMTPChannel(SMTPConfig(host="smtp.example.com"), Sender(email="x@y.com"))

    with pytest.raises(SendError, match="SMTP delivery failed"):
        await channel.send(_ENVELOPE)

    assert sock.closed is True


async def test_smtp_closes_pinned_socket_when_delivery_is_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SocketDouble:
        closed = False

        def close(self) -> None:
            self.closed = True

    sock = SocketDouble()

    async def fake_connect(_: list[str], __: int, ___: float) -> SocketDouble:
        return sock

    async def cancelled_send(_: object, **__: object) -> tuple[dict[str, object], str]:
        raise asyncio.CancelledError

    monkeypatch.setattr(email_module, "_connect_vetted_socket", fake_connect)
    monkeypatch.setattr(aiosmtplib, "send", cancelled_send)
    channel = SMTPChannel(SMTPConfig(host="smtp.example.com"), Sender(email="x@y.com"))

    with pytest.raises(asyncio.CancelledError):
        await channel.send(_ENVELOPE)

    assert sock.closed is True


async def test_smtp_dns_answer_is_pinned_without_second_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolutions = 0
    captured: dict[str, object] = {}

    async def rebind_after_validation(_: str) -> list[urls.IpAddress]:
        nonlocal resolutions
        resolutions += 1
        answer = "93.184.216.34" if resolutions == 1 else "169.254.169.254"
        return [ipaddress.ip_address(answer)]

    class SocketDouble:
        def close(self) -> None:
            pass

    sock = SocketDouble()

    async def fake_connect(addresses: list[str], port: int, timeout_seconds: float) -> SocketDouble:
        captured.update(addresses=addresses, port=port, timeout=timeout_seconds)
        return sock

    async def fake_send(_: object, **kwargs: object) -> tuple[dict[str, object], str]:
        captured.update(send=kwargs)
        return {}, "ok"

    monkeypatch.setattr(urls, "_resolve", rebind_after_validation)
    monkeypatch.setattr(email_module, "_connect_vetted_socket", fake_connect)
    monkeypatch.setattr(aiosmtplib, "send", fake_send)

    channel = SMTPChannel(
        SMTPConfig(host="smtp.rebind.example", port=465, security="ssl"),
        Sender(email="x@y.com"),
    )
    await channel.send(_ENVELOPE)

    assert resolutions == 1
    assert captured["addresses"] == ["93.184.216.34"]
    send = captured["send"]
    assert send["hostname"] == "smtp.rebind.example"
    assert send["sock"] is sock
    assert send["use_tls"] is True
    assert send["validate_certs"] is True


async def test_smtp_refuses_mixed_public_and_internal_dns_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def mixed_resolution(_: str) -> list[urls.IpAddress]:
        return [
            ipaddress.ip_address("2001:4860:4860::8888"),
            ipaddress.ip_address("fd00::1"),
        ]

    async def must_not_connect(_: list[str], __: int, ___: float) -> socket.socket:
        raise AssertionError("SMTP connector must not run for a mixed DNS answer")

    monkeypatch.setattr(urls, "_resolve", mixed_resolution)
    monkeypatch.setattr(email_module, "_connect_vetted_socket", must_not_connect)
    channel = SMTPChannel(SMTPConfig(host="smtp.example.com"), Sender(email="x@y.com"))

    with pytest.raises(SendError, match="non-public"):
        await channel.send(_ENVELOPE)


async def test_vetted_socket_connector_uses_literal_ipv4_and_ipv6(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[tuple[object, object]] = []

    class SocketDouble:
        def __init__(self, family: int, kind: int) -> None:
            self.family = family
            self.kind = kind
            self.closed = False

        def setblocking(self, value: bool) -> None:
            assert value is False

        def close(self) -> None:
            self.closed = True

    class LoopDouble:
        def time(self) -> float:
            return 100.0

        async def sock_connect(self, sock: SocketDouble, target: object) -> None:
            attempts.append((sock, target))
            if sock.family == socket.AF_INET:
                raise OSError("IPv4 route unavailable")

    loop = LoopDouble()
    monkeypatch.setattr(email_module.asyncio, "get_running_loop", lambda: loop)
    monkeypatch.setattr(email_module.socket, "socket", SocketDouble)

    connected = await email_module._connect_vetted_socket(
        ["93.184.216.34", "2001:4860:4860::8888"],
        587,
        2.0,
    )

    assert connected.family == socket.AF_INET6
    assert attempts[0][1] == ("93.184.216.34", 587)
    assert attempts[1][1] == ("2001:4860:4860::8888", 587, 0, 0)
    assert attempts[0][0].closed is True


async def test_vetted_socket_connector_closes_candidate_when_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []

    class SocketDouble:
        def __init__(self, family: int, kind: int) -> None:
            self.family = family
            self.kind = kind
            self.closed = False
            created.append(self)

        def setblocking(self, _: bool) -> None:
            pass

        def close(self) -> None:
            self.closed = True

    class LoopDouble:
        def time(self) -> float:
            return 100.0

        async def sock_connect(self, _: SocketDouble, __: object) -> None:
            raise asyncio.CancelledError

    monkeypatch.setattr(email_module.asyncio, "get_running_loop", lambda: LoopDouble())
    monkeypatch.setattr(email_module.socket, "socket", SocketDouble)

    with pytest.raises(asyncio.CancelledError):
        await email_module._connect_vetted_socket(["93.184.216.34"], 587, 2.0)

    assert len(created) == 1
    assert created[0].closed is True


async def test_test_email_endpoint_cannot_probe_internal_hosts(
    admin_client: httpx.AsyncClient,
) -> None:
    # An admin (on a public deploy, any self-registered tenant) points SMTP at the
    # metadata IP and asks for a test send. The server must refuse, not connect.
    await admin_client.post("/api/auth/step-up", json={"password": "supersecret123"})
    update = await admin_client.put(
        "/api/settings",
        json={"email_provider": "smtp", "smtp_host": "169.254.169.254", "smtp_port": 80},
    )
    assert update.status_code == 200

    response = await admin_client.post("/api/settings/test-email", json={"to": "ops@example.com"})

    assert response.status_code == 200
    body = response.json()
    assert body["delivered"] is False
    assert body["detail"] == "Email delivery failed."
    assert "169.254.169.254" not in response.text
