"""Validate that a monitored URL is safe for the server to fetch.

The server visits arbitrary user-supplied URLs in a real browser, which is a
classic SSRF vector: a URL pointing at ``localhost`` or a cloud metadata address
could reach internal services. This rejects non-HTTP schemes and any host that
is — or resolves to — a non-global (private, loopback, link-local, reserved,
shared/CGNAT, …) address. Resolution fails closed: a host that cannot be
resolved is rejected rather than waved through.

:func:`resolve_public_url` additionally returns the vetted IPs so the caller can
pin the connection to a validated address (see the capturer's DNS pinning),
closing the resolve-time-vs-connect-time rebind window.
"""

from __future__ import annotations

import asyncio
import ipaddress
from urllib.parse import urlsplit

from driftwatch.exceptions import InvalidRequest

_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost")
_NAT64_WELL_KNOWN_PREFIX = ipaddress.ip_network("64:ff9b::/96")

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class UnresolvableHost(InvalidRequest):
    """The host could not be resolved. A subclass so request handlers still map
    it to 400, while the capturer can treat it as a transient (retryable) miss
    rather than a hard SSRF block."""


async def validate_public_url(raw: str) -> str:
    """Return the URL if it is safe to fetch, else raise ``InvalidRequest``."""
    url, _addresses = await resolve_public_url(raw)
    return url


async def resolve_public_url(raw: str) -> tuple[str, list[str]]:
    """Validate the URL and return ``(url, vetted_ip_strings)``.

    DNS resolution is awaited so a slow resolver never blocks the event loop.
    """
    url = raw.strip()
    try:
        parsed = urlsplit(url)
        # Accessing ``port`` performs urllib's range and numeric validation.
        _ = parsed.port
    except ValueError as exc:
        raise InvalidRequest("URL is invalid") from exc
    if parsed.scheme not in ("http", "https"):
        raise InvalidRequest("URL must start with http:// or https://")

    host = parsed.hostname
    if not host:
        raise InvalidRequest("URL is missing a host")
    if parsed.username is not None or parsed.password is not None:
        raise InvalidRequest("URL must not contain embedded credentials")

    return url, await validate_public_host(host)


async def validate_public_host(host: str) -> list[str]:
    """Ensure a bare host or IP — an SMTP server, say — is publicly routable, not
    a loopback/private/link-local/metadata address, and return its vetted IPs.

    The URL guard covers schemed endpoints (webhooks, monitored pages); this is
    the same defence for a host that arrives without a scheme, so a tenant cannot
    aim an outbound connection at the host's own internal network.
    """
    lowered = host.strip().lower()
    if not lowered:
        raise InvalidRequest("host is missing")
    if any(
        character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F
        for character in lowered
    ):
        raise InvalidRequest("host contains invalid characters")
    if lowered == "localhost" or lowered.endswith(_BLOCKED_SUFFIXES):
        raise InvalidRequest("host points at a non-public address")

    addresses = await _resolve(lowered)
    if not addresses:
        raise UnresolvableHost("host could not be resolved")
    for address in addresses:
        if _is_blocked(address):
            raise InvalidRequest("host resolves to a non-public address")
    return list(dict.fromkeys(str(address) for address in addresses))


async def _resolve(host: str) -> list[IpAddress]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    except (OSError, UnicodeError):
        return []  # fail closed: resolve_public_url rejects an empty result
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def _is_blocked(address: IpAddress) -> bool:
    # Default-deny: anything not globally routable (private, loopback, link-local,
    # reserved, and CGNAT/shared 100.64.0.0/10) is rejected in one rule.
    if not address.is_global or address.is_multicast or address.is_unspecified:
        return True
    if not isinstance(address, ipaddress.IPv6Address):
        return False

    # Keep the result stable across Python/ipaddress versions and reject
    # transition forms that embed a blocked IPv4 endpoint inside a globally
    # shaped IPv6 literal.
    embedded = [address.ipv4_mapped, address.sixtofour]
    if address.teredo is not None:
        embedded.extend(address.teredo)
    if address in _NAT64_WELL_KNOWN_PREFIX:
        embedded.append(ipaddress.IPv4Address(int(address) & 0xFFFFFFFF))
    return any(candidate is not None and _is_blocked(candidate) for candidate in embedded)
