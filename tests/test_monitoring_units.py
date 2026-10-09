"""Unit tests for the pure parts of the pipeline."""

from __future__ import annotations

from driftwatch.monitoring.cleaner import clean_dom
from driftwatch.monitoring.differ import html_diff, unified_text_diff
from driftwatch.monitoring.extractor import canonical_text, diff_blocks, extract_blocks
from driftwatch.monitoring.prompts import (
    DEFAULT_IMPORTANCE_RULES,
    build_system_prompt,
    resolve_importance_rules,
)
from driftwatch.monitoring.usage import TokenUsage, estimate_cost


def test_clean_dom_removes_chrome_and_scripts() -> None:
    html = "<html><body><nav>menu</nav><script>x()</script><p>Hello world</p></body></html>"
    cleaned = clean_dom(html)
    assert "menu" not in cleaned
    assert "x()" not in cleaned
    assert "Hello world" in cleaned


def test_clean_dom_preserves_business_identifiers() -> None:
    first = clean_dom("<p>Order 1709568000000 placed</p>")
    second = clean_dom("<p>Order 1709570000000 placed</p>")
    assert first != second
    assert "1709568000000" in first


def test_clean_dom_honours_ignore_selectors() -> None:
    html = '<div class="ad">buy now</div><p>real content here</p>'
    cleaned = clean_dom(html, ignore_selectors=[".ad"])
    assert "buy now" not in cleaned
    assert "real content here" in cleaned


def test_extract_blocks_classifies_and_preserves_short_text() -> None:
    blocks = extract_blocks("<h1>Title</h1><p>ok</p><p>A real paragraph of content</p>")
    kinds = {block.kind for block in blocks}
    assert "heading" in kinds
    assert any(block.text == "ok" for block in blocks)


def test_diff_blocks_detects_added_and_removed_but_ignores_reorder() -> None:
    old = extract_blocks("<p>First paragraph here</p><p>Second paragraph here</p>")
    reordered = extract_blocks("<p>Second paragraph here</p><p>First paragraph here</p>")
    assert not diff_blocks(old, reordered).has_changes

    changed = extract_blocks("<p>First paragraph here</p><p>A brand new paragraph</p>")
    diff = diff_blocks(old, changed)
    assert any("brand new" in block.text for block in diff.added)
    assert any("Second paragraph" in block.text for block in diff.removed)


def test_link_href_change_is_detected_even_when_label_is_unchanged() -> None:
    old = extract_blocks('<a href="/report-2024.pdf">Annual report</a>')
    new = extract_blocks('<a href="/report-2025.pdf">Annual report</a>')
    diff = diff_blocks(old, new)
    assert any("report-2025.pdf" in block.text for block in diff.added)


def test_link_normalisation_drops_tracking_params() -> None:
    with_utm = extract_blocks('<a href="/p?utm_source=x&id=7">Doc link</a>')
    without = extract_blocks('<a href="/p?id=7">Doc link</a>')
    assert canonical_text(with_utm) == canonical_text(without)


def test_html_diff_escapes_page_content() -> None:
    markup = html_diff("safe line", "<script>alert(1)</script>")
    assert "<script>" not in markup
    assert "&lt;script&gt;" in markup
    assert "diff-added" in markup


def test_unified_text_diff_marks_changed_lines() -> None:
    diff = unified_text_diff("alpha\nbeta", "alpha\ngamma")
    assert "-beta" in diff
    assert "+gamma" in diff


def test_importance_rules_follow_inheritance_order() -> None:
    assert (
        resolve_importance_rules(
            site_prompt="site rule", project_prompt="project rule", global_rules="global rule"
        ).source
        == "site"
    )
    assert (
        resolve_importance_rules(
            site_prompt=None, project_prompt="project rule", global_rules="global rule"
        ).source
        == "project"
    )
    assert (
        resolve_importance_rules(
            site_prompt=None, project_prompt=None, global_rules="global rule"
        ).source
        == "global"
    )
    fallback = resolve_importance_rules(site_prompt=None, project_prompt=None, global_rules=None)
    assert fallback.source == "default"
    assert fallback.text == DEFAULT_IMPORTANCE_RULES


def test_build_system_prompt_includes_rules_and_source() -> None:
    rules = resolve_importance_rules(
        site_prompt="watch prices", project_prompt=None, global_rules=None
    )
    prompt = build_system_prompt(rules)
    assert "watch prices" in prompt
    assert "source: site" in prompt


def test_estimate_cost_uses_per_million_pricing() -> None:
    estimate = estimate_cost("gpt-4o-mini", TokenUsage(1_000_000, 0))
    assert estimate.cost_usd == 0.15
    assert estimate.usage.total_tokens == 1_000_000


def test_estimate_cost_does_not_invent_unknown_model_price() -> None:
    estimate = estimate_cost("some-future-model", TokenUsage(0, 1_000_000))
    assert estimate.cost_usd is None
    assert estimate.pricing_source == "unknown"
