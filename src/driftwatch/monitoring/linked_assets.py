"""Watch documents linked from a monitored page for in-place changes.

A PDF replaced under the same URL is invisible to the page diff: the link
block's text (label and href) does not change. When an organization opts in
(the ``watch_linked_documents`` setting), the check pipeline HEAD-probes
document-looking links with a short timeout and fingerprints the validator
headers (ETag, Last-Modified, Content-Length). A changed fingerprint
synthesizes an added ``[document]`` content block, which feeds the existing
diff -> ChangeEvent -> analyzer path like any page change. Probe failures are
skipped silently — a flaky file server must never fail the page check.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.exceptions import InvalidRequest
from driftwatch.models import LinkedAsset, Site
from driftwatch.monitoring.extractor import ContentBlock
from driftwatch.security.outbound import resolve_pinned_http_endpoint

logger = logging.getLogger(__name__)

DOCUMENT_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odt"})
# Bound the per-check probe count so a page full of documents cannot stall the
# (serial) scheduler tick with dozens of outbound requests.
MAX_ASSETS_PER_SITE = 20
_HEAD_TIMEOUT_SECONDS = 5.0
_MAX_REDIRECTS = 5
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
# Link blocks render as "label [href]" (or as a bare href when the link has no
# visible text); this pulls the trailing bracketed href back out.
_HREF_IN_BLOCK = re.compile(r"\[([^\[\]]+)\]$")


def collect_document_urls(
    blocks: list[ContentBlock], base_url: str, *, cap: int = MAX_ASSETS_PER_SITE
) -> list[str]:
    """Absolute http(s) URLs of document links among ``blocks``, capped."""
    urls: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        if block.kind != "link":
            continue
        match = _HREF_IN_BLOCK.search(block.text)
        href = match.group(1) if match else block.text
        absolute = urljoin(base_url, href.strip())
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https"):
            continue
        if not any(parts.path.lower().endswith(ext) for ext in DOCUMENT_EXTENSIONS):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        urls.append(absolute)
        if len(urls) >= cap:
            break
    return urls


@dataclass(frozen=True, slots=True)
class _Fingerprint:
    etag: str | None
    last_modified: str | None
    content_length: int | None

    @property
    def blank(self) -> bool:
        """The server sent no validators at all — nothing to compare against."""
        return self.etag is None and self.last_modified is None and self.content_length is None


class LinkedDocumentChecker:
    """The pipeline's ``document_checker`` hook, backed by concurrent HEADs.

    Tests inject an ``httpx.MockTransport``; production uses the default
    transport with a short timeout so slow file hosts cannot hold up a check.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = _HEAD_TIMEOUT_SECONDS,
        max_assets: int = MAX_ASSETS_PER_SITE,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._max_assets = max_assets
        self._transport = transport

    async def __call__(
        self, session: AsyncSession, site: Site, blocks: list[ContentBlock]
    ) -> list[ContentBlock]:
        urls = collect_document_urls(blocks, site.url, cap=self._max_assets)
        known = {
            asset.url: asset
            for asset in (
                await session.execute(select(LinkedAsset).where(LinkedAsset.site_id == site.id))
            ).scalars()
        }
        # Drop rows for links no longer on the page: removal itself is already
        # visible to the page diff through the vanished link block, and pruning
        # keeps the table bounded by what the page currently links to.
        current = set(urls)
        for stale_url, stale_asset in known.items():
            if stale_url not in current:
                await session.delete(stale_asset)

        fingerprints = await self._probe(urls)
        now = datetime.now(UTC)
        changed: list[ContentBlock] = []
        for url in urls:
            fingerprint = fingerprints.get(url)
            if fingerprint is None:
                continue  # HEAD failed — skipped silently, retried next check
            asset = known.get(url)
            if asset is None:
                # First sighting: record the baseline. The link's appearance on
                # the page is already a page-level change; no synthetic block.
                session.add(
                    LinkedAsset(
                        site_id=site.id,
                        url=url,
                        etag=fingerprint.etag,
                        last_modified=fingerprint.last_modified,
                        content_length=fingerprint.content_length,
                        checked_at=now,
                    )
                )
                continue
            previous = _Fingerprint(asset.etag, asset.last_modified, asset.content_length)
            asset.checked_at = now
            if fingerprint.blank or fingerprint == previous:
                continue
            # Only a change *between* two observed fingerprints counts; a server
            # that just started sending validators is a baseline, not an update.
            if not previous.blank:
                changed.append(ContentBlock(kind="document", tag="a", text=f"{url} updated"))
            asset.etag = fingerprint.etag
            asset.last_modified = fingerprint.last_modified
            asset.content_length = fingerprint.content_length
        return changed

    async def _probe(self, urls: list[str]) -> dict[str, _Fingerprint]:
        if not urls:
            return {}
        if self._transport is not None:
            client = httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=False, transport=self._transport
            )
        else:
            client = httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=False,
                limits=httpx.Limits(max_keepalive_connections=0),
                trust_env=False,
            )
        async with client:
            results = await asyncio.gather(*(self._head(client, url) for url in urls))
        return {url: fp for url, fp in zip(urls, results, strict=True) if fp is not None}

    @staticmethod
    async def _head(client: httpx.AsyncClient, url: str) -> _Fingerprint | None:
        # The URL came off a monitored page (attacker-influenced content), so it
        # gets the same SSRF vetting as everything else the server fetches. Do
        # not delegate redirects to httpx: every hop is attacker-controlled and
        # must be validated before a socket is opened.
        current = url
        visited: set[str] = set()
        for redirect_count in range(_MAX_REDIRECTS + 1):
            if current in visited:
                return None
            visited.add(current)
            try:
                endpoint = await resolve_pinned_http_endpoint(current)
            except InvalidRequest:
                return None
            request = client.build_request("HEAD", endpoint.logical_url)
            endpoint.pin(request)
            try:
                response = await client.send(request, stream=True)
            except httpx.HTTPError as exc:
                # Provider errors often include the full (possibly secret)
                # document URL.  The exception class is sufficient diagnostics.
                logger.debug("HEAD document probe failed (%s)", type(exc).__name__)
                return None
            try:
                if response.status_code in _REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if location is None or redirect_count >= _MAX_REDIRECTS:
                        return None
                    # Resolve relative locations against the logical URL, not
                    # the literal transport URL used for connection pinning.
                    current = urljoin(current, location)
                    continue
                if response.status_code >= 400:
                    return None
                length = response.headers.get("content-length")
                return _Fingerprint(
                    etag=response.headers.get("etag"),
                    last_modified=response.headers.get("last-modified"),
                    content_length=int(length) if length and length.isdigit() else None,
                )
            finally:
                await response.aclose()
        return None
