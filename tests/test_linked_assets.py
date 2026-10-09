"""Linked-document watching: fingerprint changes, opt-in gating, cap, failures."""

from __future__ import annotations

import ipaddress

import httpx
import pytest
from sqlalchemy import select

import driftwatch.security.urls as urls
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.models import ChangeEvent, LinkedAsset, Setting, Site, Snapshot
from driftwatch.monitoring.extractor import ContentBlock, extract_blocks
from driftwatch.monitoring.linked_assets import LinkedDocumentChecker, collect_document_urls
from driftwatch.monitoring.pipeline import CheckStatus
from driftwatch.runner import SiteRunner
from driftwatch.settings_store import SettingsStore
from tests.conftest import RecordingChannel, ScriptedCapturer, StubAnalyzer, create_org

_PAGE = (
    "<html><body><h1>Docs</h1><p>Some intro paragraph body</p>"
    '<a href="/files/report.pdf">Quarterly report</a></body></html>'
)
_DOC_URL = "https://example.test/files/report.pdf"


class _HeadServer:
    """MockTransport handler with a switchable ETag and a request counter."""

    def __init__(self, etag: str = "v1") -> None:
        self.etag = etag
        self.requests = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        assert request.method == "HEAD"
        return httpx.Response(200, headers={"ETag": self.etag, "Content-Length": "1000"})


async def _add_site(database: Database, *, watch: bool) -> int:
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(url="https://example.test/docs", name="Docs", organization_id=org_id)
        session.add(site)
        if watch:
            session.add(Setting(key="watch_linked_documents", value="true"))
        await session.flush()
        site_id = site.id
        await session.commit()
        return site_id


async def test_document_replacement_synthesizes_a_change(
    database: Database, settings: Settings, channel: RecordingChannel
) -> None:
    server = _HeadServer(etag="v1")
    runner = SiteRunner(
        database,
        ScriptedCapturer(html=_PAGE),
        settings,
        analyzer=StubAnalyzer(),
        channel=channel,
        document_checker=LinkedDocumentChecker(transport=httpx.MockTransport(server)),
    )
    site_id = await _add_site(database, watch=True)

    first = await runner.run(site_id)  # baseline: fingerprint seeded
    assert first.status is CheckStatus.BASELINE

    second = await runner.run(site_id)  # same page, same ETag
    assert second.status is CheckStatus.UNCHANGED

    server.etag = "v2"  # the PDF was replaced under the same URL
    third = await runner.run(site_id)
    assert third.status is CheckStatus.CHANGED
    assert third.change_id is not None

    async with database.session() as session:
        change = await session.get(ChangeEvent, third.change_id)
        snapshots = (await session.execute(select(Snapshot))).scalars().all()
        asset = (await session.execute(select(LinkedAsset))).scalar_one()
    assert change is not None
    assert f"[document] {_DOC_URL} updated" in change.diff_text
    assert len(snapshots) == 1  # the page itself never changed
    assert asset.etag == "v2"  # the new fingerprint became the baseline
    assert server.requests == 3


async def test_watching_is_off_by_default(
    database: Database, settings: Settings, channel: RecordingChannel
) -> None:
    server = _HeadServer()
    runner = SiteRunner(
        database,
        ScriptedCapturer(html=_PAGE),
        settings,
        analyzer=StubAnalyzer(),
        channel=channel,
        document_checker=LinkedDocumentChecker(transport=httpx.MockTransport(server)),
    )
    site_id = await _add_site(database, watch=False)

    await runner.run(site_id)
    result = await runner.run(site_id)

    assert result.status is CheckStatus.UNCHANGED
    assert server.requests == 0  # nothing probed without the opt-in
    async with database.session() as session:
        assert (await session.execute(select(LinkedAsset))).scalars().all() == []
        store = SettingsStore(session, runner._box)
        assert await store.watch_linked_documents() is False


async def test_document_url_collection_is_capped_and_filtered() -> None:
    blocks = [
        ContentBlock(kind="link", tag="a", text=f"Doc {index} [/files/doc-{index:02d}.pdf]")
        for index in range(25)
    ]
    blocks.append(ContentBlock(kind="link", tag="a", text="Page [/about.html]"))
    blocks.append(ContentBlock(kind="paragraph", tag="p", text="Not a link at all"))

    urls = collect_document_urls(blocks, "https://example.test/docs")

    assert len(urls) == 20
    assert urls[0] == "https://example.test/files/doc-00.pdf"
    assert all(url.endswith(".pdf") for url in urls)


async def test_head_failures_are_skipped_silently(database: Database) -> None:
    def exploding(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("file server is down", request=request)

    checker = LinkedDocumentChecker(transport=httpx.MockTransport(exploding))
    site_id = await _add_site(database, watch=True)

    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        blocks = extract_blocks(_PAGE)
        changed = await checker(session, site, blocks)
        await session.commit()

    assert changed == []
    async with database.session() as session:
        # No fingerprint recorded — the probe is simply retried next check.
        assert (await session.execute(select(LinkedAsset))).scalars().all() == []


async def test_document_redirect_to_private_network_is_blocked_before_request() -> None:
    requested: list[str] = []

    def redirecting(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/internal.pdf"})

    checker = LinkedDocumentChecker(transport=httpx.MockTransport(redirecting))
    fingerprints = await checker._probe([_DOC_URL])

    assert fingerprints == {}
    assert requested == ["https://93.184.216.34/files/report.pdf"]


async def test_document_redirect_revalidates_and_accepts_public_relative_target() -> None:
    requested: list[str] = []

    def redirecting(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path == "/files/report.pdf":
            return httpx.Response(307, headers={"Location": "latest/report.pdf"})
        return httpx.Response(200, headers={"ETag": "v2", "Content-Length": "42"})

    checker = LinkedDocumentChecker(transport=httpx.MockTransport(redirecting))
    fingerprints = await checker._probe([_DOC_URL])

    assert requested == [
        "https://93.184.216.34/files/report.pdf",
        "https://93.184.216.34/files/latest/report.pdf",
    ]
    assert fingerprints[_DOC_URL].etag == "v2"
    assert fingerprints[_DOC_URL].content_length == 42


async def test_document_redirect_loop_is_bounded() -> None:
    requests = 0

    def looping(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        target = "/files/b.pdf" if request.url.path.endswith("report.pdf") else _DOC_URL
        return httpx.Response(302, headers={"Location": target})

    checker = LinkedDocumentChecker(transport=httpx.MockTransport(looping))

    assert await checker._probe([_DOC_URL]) == {}
    assert requests == 2


async def test_document_probe_pins_dns_answer_and_preserves_http_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolutions = 0
    captured: dict[str, object] = {}

    async def rebind_after_validation(_: str) -> list[urls.IpAddress]:
        nonlocal resolutions
        resolutions += 1
        answer = "93.184.216.34" if resolutions == 1 else "127.0.0.1"
        return [ipaddress.ip_address(answer)]

    def server(request: httpx.Request) -> httpx.Response:
        captured.update(
            url=str(request.url),
            host=request.headers["host"],
            connection=request.headers["connection"],
            sni=request.extensions["sni_hostname"],
        )
        return httpx.Response(200, headers={"ETag": "v1"})

    monkeypatch.setattr(urls, "_resolve", rebind_after_validation)
    checker = LinkedDocumentChecker(transport=httpx.MockTransport(server))

    fingerprints = await checker._probe([_DOC_URL])

    assert resolutions == 1
    assert captured == {
        "url": "https://93.184.216.34/files/report.pdf",
        "host": "example.test",
        "connection": "close",
        "sni": "example.test",
    }
    assert fingerprints[_DOC_URL].etag == "v1"
