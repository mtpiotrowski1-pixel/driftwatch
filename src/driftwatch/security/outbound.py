"""Connection pinning for outbound HTTP requests to untrusted destinations.

URL validation and socket connection must use the same DNS answer.  Otherwise
an attacker can return a public address during validation and an internal one
when the HTTP client resolves the hostname again.  This module rewrites only
the transport URL to a vetted literal IP while preserving the logical Host
header and TLS server name used for certificate verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from driftwatch.exceptions import InvalidRequest
from driftwatch.security.urls import resolve_public_url


@dataclass(frozen=True, slots=True)
class PinnedHTTPEndpoint:
    """A logical URL and the public IP selected for its next connection."""

    logical_url: str
    address: str
    tls_server_name: str

    def pin(self, request: httpx.Request) -> None:
        """Mutate a request built for ``logical_url`` to connect to ``address``.

        ``httpx`` creates the correct Host header while building the logical
        request.  Changing ``Request.url`` afterwards leaves that header intact.
        ``httpcore`` consumes ``sni_hostname`` for both TLS SNI and hostname/
        certificate verification, so HTTPS still authenticates the configured
        hostname rather than the literal connection address.
        """
        request.url = request.url.copy_with(host=self.address)
        request.extensions["sni_hostname"] = self.tls_server_name
        # A pinned-IP origin can be shared by unrelated logical hostnames.  Do
        # not let a pooled HTTP/1.1 connection authenticated for one hostname be
        # reused for another hostname that happens to resolve to the same IP.
        request.headers["Connection"] = "close"


async def resolve_pinned_http_endpoint(raw_url: str) -> PinnedHTTPEndpoint:
    """Resolve and validate ``raw_url`` once, returning a connection pin."""
    candidate = raw_url.strip()
    try:
        logical = httpx.URL(candidate)
    except httpx.InvalidURL as exc:
        raise InvalidRequest("URL is invalid") from exc
    logical_url, addresses = await resolve_public_url(candidate)
    validated_host = urlsplit(logical_url).hostname
    if validated_host is None or logical.host.casefold() != validated_host.casefold():
        # Fail closed if urllib (the validation parser) and httpx (the transport
        # parser) ever disagree about which authority the URL names.
        raise InvalidRequest("URL host is ambiguous")
    # ``resolve_public_url`` guarantees at least one address.  Keep the
    # defensive branch local in case that lower-level contract ever changes.
    if not addresses:  # pragma: no cover - guarded by validate_public_host
        raise RuntimeError("public URL resolution returned no addresses")
    return PinnedHTTPEndpoint(
        logical_url=logical_url,
        address=addresses[0],
        tls_server_name=logical.raw_host.decode("ascii"),
    )
