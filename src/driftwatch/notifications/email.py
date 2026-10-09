"""Email delivery channels behind a single protocol.

The dispatcher depends on :class:`EmailChannel`, so it neither knows nor cares
whether mail goes out over SMTP, the Brevo HTTP API, or — in development — the
log. Each channel returns a provider message id on success and raises
:class:`SendError` on failure so the dispatcher can record per-recipient status.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from dataclasses import dataclass
from email.message import EmailMessage as MIMEEmail
from email.utils import formataddr
from hashlib import sha256
from typing import TYPE_CHECKING, Protocol
from uuid import NAMESPACE_URL, uuid5

from driftwatch.enums import EmailChannelName
from driftwatch.exceptions import InvalidRequest
from driftwatch.security.urls import validate_public_host

if TYPE_CHECKING:
    from driftwatch.settings_store import EmailConfig

logger = logging.getLogger(__name__)


class SendError(Exception):
    """A channel failed to hand the message to its provider."""


class EmailConfigurationError(SendError):
    """The selected provider has no usable configuration."""


def default_sender_email(base_url: str) -> str:
    """Fallback ``From`` address derived from the deployment host, used when no
    sender is configured in settings."""
    host = base_url.split("//")[-1].split("/")[0].split(":")[0] or "localhost"
    return f"driftwatch@{host}"


@dataclass(frozen=True, slots=True)
class EmailEnvelope:
    to: str
    subject: str
    html_body: str
    text_body: str
    to_name: str | None = None
    # Stable across retries. SMTP receives a deterministic Message-ID; API
    # providers receive their native idempotency value where supported.
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class Sender:
    email: str
    name: str = "Driftwatch"


class EmailChannel(Protocol):
    name: EmailChannelName

    async def send(self, envelope: EmailEnvelope) -> str: ...


@dataclass(frozen=True, slots=True)
class SMTPConfig:
    host: str
    port: int = 587
    username: str | None = None
    password: str | None = None
    security: str = "starttls"  # starttls | ssl | none
    timeout: float = 15.0


class SMTPChannel:
    name = EmailChannelName.SMTP

    def __init__(self, config: SMTPConfig, sender: Sender) -> None:
        self._config = config
        self._sender = sender

    async def send(self, envelope: EmailEnvelope) -> str:
        import aiosmtplib

        # The host is tenant-supplied, so guard it like the webhook URL: refuse a
        # server that resolves to a loopback/private/metadata address before we
        # connect, so test-email can't be turned into an internal port probe.
        host = self._config.host.strip()
        try:
            addresses = await validate_public_host(host)
        except InvalidRequest as exc:
            raise SendError(f"refused to connect to a non-public SMTP host: {exc}") from exc

        message = _build_mime(envelope, self._sender)
        try:
            connected_socket = await _connect_vetted_socket(
                addresses,
                self._config.port,
                self._config.timeout,
            )
        except (OSError, TimeoutError) as exc:
            raise SendError("SMTP delivery failed") from exc
        try:
            await aiosmtplib.send(
                message,
                # ``sock`` prevents aiosmtplib from resolving ``hostname`` a
                # second time.  It still uses the original hostname below for
                # implicit TLS and STARTTLS SNI/certificate verification.
                hostname=host,
                sock=connected_socket,
                username=self._config.username,
                password=self._config.password,
                start_tls=self._config.security == "starttls",
                use_tls=self._config.security == "ssl",
                validate_certs=True,
                timeout=self._config.timeout,
            )
        except (aiosmtplib.SMTPException, OSError, TimeoutError) as exc:
            # The library normally owns the supplied socket once its coroutine
            # starts.  Close defensively on failure as well, including failures
            # that occur before asyncio has created the transport.
            connected_socket.close()
            raise SendError("SMTP delivery failed") from exc
        except BaseException:
            connected_socket.close()
            raise
        return message["Message-ID"] or ""


class BrevoChannel:
    name = EmailChannelName.BREVO
    _ENDPOINT = "https://api.brevo.com/v3/smtp/email"

    def __init__(self, api_key: str, sender: Sender) -> None:
        self._api_key = api_key
        self._sender = sender

    async def send(self, envelope: EmailEnvelope) -> str:
        import httpx

        payload = {
            "sender": {"email": self._sender.email, "name": self._sender.name},
            "to": [{"email": envelope.to, "name": envelope.to_name or envelope.to}],
            "subject": envelope.subject,
            "htmlContent": envelope.html_body,
            "textContent": envelope.text_body,
        }
        if envelope.idempotency_key:
            payload["headers"] = {
                # Brevo requires this exact body-header name and a UUID. UUIDv5
                # preserves retry stability for Driftwatch's arbitrary keys
                # without exposing the internal queue identifier.
                "idempotencyKey": _brevo_idempotency_key(envelope.idempotency_key),
            }
        headers = {"api-key": self._api_key, "content-type": "application/json"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(self._ENDPOINT, json=payload, headers=headers)
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = None
        if response.status_code >= 400:
            if (
                envelope.idempotency_key
                and isinstance(response_payload, dict)
                and response_payload.get("code") == "duplicate_parameter"
            ):
                # The provider accepted the same logical request earlier but
                # the caller may have lost its response. Treat its explicit
                # duplicate acknowledgement as successful handoff.
                return "brevo-idempotent-duplicate"
            # Provider bodies may echo recipient or message content. Keep the
            # exception safe even for callers that accidentally log it.
            raise SendError(f"brevo returned HTTP {response.status_code}")
        if not isinstance(response_payload, dict):
            raise SendError("brevo returned an invalid success response")
        message_id = response_payload.get("messageId")
        if not isinstance(message_id, str) or not message_id:
            raise SendError("brevo success response omitted its message id")
        return message_id


class LogChannel:
    """Records delivery metadata without logging message content or reset tokens."""

    name = EmailChannelName.LOG

    async def send(self, envelope: EmailEnvelope) -> str:
        recipient_domain = envelope.to.rpartition("@")[2] or "invalid"
        logger.info(
            "[email:log] recipient_domain=%s subject_chars=%d body_chars=%d",
            recipient_domain,
            len(envelope.subject),
            len(envelope.text_body),
        )
        return "logged"


class UnconfiguredChannel:
    """Persist a delivery failure instead of pretending a provider sent mail."""

    def __init__(self, name: EmailChannelName) -> None:
        self.name = name

    async def send(self, envelope: EmailEnvelope) -> str:
        raise EmailConfigurationError(f"{self.name.value} email is not configured")


def build_channel(config: EmailConfig) -> EmailChannel:
    """Log only when deliberately selected; incomplete providers fail closed."""
    sender = Sender(email=config.from_email, name=config.from_name)
    if config.channel is EmailChannelName.BREVO:
        if not config.brevo_api_key or not config.brevo_api_key.strip():
            return UnconfiguredChannel(EmailChannelName.BREVO)
        return BrevoChannel(config.brevo_api_key, sender)
    if config.channel is EmailChannelName.SMTP:
        if not config.smtp_host or not config.smtp_host.strip():
            return UnconfiguredChannel(EmailChannelName.SMTP)
        return SMTPChannel(
            SMTPConfig(
                host=config.smtp_host,
                port=config.smtp_port,
                username=config.smtp_username,
                password=config.smtp_password,
                security=config.smtp_security,
            ),
            sender,
        )
    if config.channel is EmailChannelName.LOG:
        return LogChannel()
    return UnconfiguredChannel(config.channel)


def _build_mime(envelope: EmailEnvelope, sender: Sender) -> MIMEEmail:
    message = MIMEEmail()
    message["From"] = formataddr((sender.name, sender.email))
    message["To"] = formataddr((envelope.to_name or "", envelope.to))
    # Strip CR/LF so a crafted subject/headline can't attempt SMTP header
    # injection (and can't raise on the email lib's header-validation either).
    message["Subject"] = envelope.subject.replace("\r", " ").replace("\n", " ")
    if envelope.idempotency_key:
        message["Message-ID"] = _message_id(envelope.idempotency_key, sender.email)
    message.set_content(envelope.text_body)
    message.add_alternative(envelope.html_body, subtype="html")
    return message


def _message_id(idempotency_key: str, sender_email: str) -> str:
    digest = sha256(idempotency_key.encode("utf-8")).hexdigest()
    domain = sender_email.rpartition("@")[2] or "localhost"
    return f"<dw-{digest}@{domain}>"


def _brevo_idempotency_key(idempotency_key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"driftwatch:email:{idempotency_key}"))


async def _connect_vetted_socket(
    addresses: list[str],
    port: int,
    timeout_seconds: float,
) -> socket.socket:
    """Connect only to literal vetted addresses, with bounded family failover."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    for index, raw_address in enumerate(addresses):
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        address = ipaddress.ip_address(raw_address)
        family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        target: tuple[str, int] | tuple[str, int, int, int]
        target = (raw_address, port, 0, 0) if address.version == 6 else (raw_address, port)
        candidate = socket.socket(family, socket.SOCK_STREAM)
        candidate.setblocking(False)
        # Give every remaining vetted address a chance within the overall
        # timeout instead of spending the complete budget on the first AAAA/A.
        attempt_timeout = remaining / (len(addresses) - index)
        try:
            await asyncio.wait_for(loop.sock_connect(candidate, target), attempt_timeout)
        except (OSError, TimeoutError):
            candidate.close()
            continue
        except BaseException:
            candidate.close()
            raise
        return candidate
    raise OSError("could not connect to a vetted SMTP address")
