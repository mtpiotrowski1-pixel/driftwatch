"""Requirement examples with independently declared monitoring outcomes.

The JSON fixture is the semantic contract, including deliberate noise and
counterexamples to value-only multiset comparison. Each case also goes through
the real persistence pipeline, rather than only testing the extractor helper.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from tests.conftest import ScriptedCapturer, create_org

from driftwatch.db import Database
from driftwatch.models import ChangeEvent, Site, Snapshot
from driftwatch.monitoring.capture import CapturedPage
from driftwatch.monitoring.cleaner import clean_dom
from driftwatch.monitoring.differ import MAX_HTML_DIFF_CHARS, html_diff
from driftwatch.monitoring.extractor import canonical_text, diff_blocks, extract_blocks
from driftwatch.monitoring.linked_assets import collect_document_urls
from driftwatch.monitoring.pipeline import CheckStatus, run_check

_CASES = json.loads(
    (Path(__file__).parent / "fixtures/monitoring_cases.json").read_text(encoding="utf-8-sig")
)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["id"])
def test_monitoring_semantic_contract(case: dict[str, Any]) -> None:
    old = extract_blocks(clean_dom(case["before"], ignore_selectors=case.get("ignore_selectors")))
    new = extract_blocks(clean_dom(case["after"], ignore_selectors=case.get("ignore_selectors")))
    assert diff_blocks(old, new).has_changes is case["changed"]
    if "expected_after" in case:
        assert case["expected_after"] in canonical_text(new)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["id"])
async def test_monitoring_contract_persists_only_expected_changes(
    database: Database, case: dict[str, Any]
) -> None:
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(organization_id=org_id, url="https://example.test/prices")
        session.add(site)
        await session.flush()
        capturer = ScriptedCapturer(queue=[case["before"], case["after"]])
        baseline = await run_check(
            session, site, capturer=capturer, ignore_selectors=case.get("ignore_selectors")
        )
        result = await run_check(
            session, site, capturer=capturer, ignore_selectors=case.get("ignore_selectors")
        )
        count = await session.scalar(select(func.count()).select_from(ChangeEvent))
        await session.commit()
    assert baseline.status is CheckStatus.BASELINE
    assert result.status is (CheckStatus.CHANGED if case["changed"] else CheckStatus.UNCHANGED)
    assert count == int(case["changed"])


def test_relative_document_link_uses_captured_document_base() -> None:
    # The original watched URL redirects to /en/reports/, then <base> resolves
    # to /assets/reports/. The browser passes that complete document.baseURI.
    cleaned = clean_dom(
        "<base href='../../assets/reports/'><a href='annual.pdf'>Annual report</a>",
        base_url="https://example.test/assets/reports/",
    )
    assert collect_document_urls(extract_blocks(cleaned), "https://old.example.test/watch") == [
        "https://example.test/assets/reports/annual.pdf"
    ]


def test_late_change_is_visible_after_a_large_unchanged_prefix() -> None:
    prefix = "\n".join(f"unchanged row {i} " + "x" * 80 for i in range(4_000))
    markup = html_diff(prefix + "\nprice 10", prefix + "\nprice 20")
    assert 'diff-removed">price 10' in markup
    assert 'diff-added">price 20' in markup
    assert len(markup) <= MAX_HTML_DIFF_CHARS


def test_oversized_changed_line_stays_visible_and_escaped() -> None:
    markup = html_diff("", "<script>price 20</script>" + "x" * MAX_HTML_DIFF_CHARS)
    assert "diff-added" in markup
    assert "diff-truncated" in markup
    assert "&lt;script&gt;price 20&lt;/script&gt;" in markup
    assert "<script>" not in markup
    assert len(markup) <= MAX_HTML_DIFF_CHARS


async def test_capture_metadata_resolves_links_before_snapshot_storage(database: Database) -> None:
    class RedirectedCapturer:
        async def capture(self, **_: Any) -> CapturedPage:
            return CapturedPage(
                "<base href='../assets/'><a href='annual.pdf'>Annual report</a>",
                "https://final.example.test/assets/",
            )

    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(organization_id=org_id, url="https://original.example.test/watch")
        session.add(site)
        await session.flush()
        outcome = await run_check(session, site, capturer=RedirectedCapturer())
        snapshot = await session.get(Snapshot, outcome.snapshot_id)
        assert snapshot is not None
        assert "https://final.example.test/assets/annual.pdf" in snapshot.content_html
        assert collect_document_urls(extract_blocks(snapshot.content_html), site.url) == [
            "https://final.example.test/assets/annual.pdf"
        ]
