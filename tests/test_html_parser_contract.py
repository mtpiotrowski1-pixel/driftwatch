"""HTML capture fragments retain domain records without a native XML parser."""

import pytest

from driftwatch.monitoring.cleaner import clean_dom
from driftwatch.monitoring.extractor import diff_blocks, extract_blocks


@pytest.mark.parametrize(
    ("html", "text"),
    [
        ("<p>Zażółć gęślą jaźń &amp; żółć</p>", "Zażółć gęślą jaźń & żółć"),
        ("<p>العربية 中文 日本語 한국어 🙂</p>", "العربية 中文 日本語 한국어 🙂"),
        ("<p>Price&nbsp;&#49; &lt; 2</p>", "Price 1 < 2"),
        ("<div><p>Available: 7", "Available: 7"),
        ("<p>Available: <strong>7</strong><br>units</p>", "Available: 7 units"),
    ],
)
def test_captured_fragments_preserve_visible_text(html: str, text: str) -> None:
    blocks = extract_blocks(clean_dom(html))
    assert any(block.text == text for block in blocks)


def test_browser_document_and_selected_fragment_have_identical_records() -> None:
    fragment = "<main><h2>Inventory</h2><table><tr><td>Milk</td><td>7</td></tr></table></main>"
    document = f"<html><head><title>Store</title></head><body>{fragment}</body></html>"
    assert extract_blocks(clean_dom(document)) == extract_blocks(clean_dom(fragment))


def test_table_records_keep_product_value_relationship_after_parser_change() -> None:
    before = "<table><tr><td>Milk</td><td>7</td></tr><tr><td>Bread</td><td>2</td></tr></table>"
    reordered = "<table><tr><td>Bread</td><td>2</td></tr><tr><td>Milk</td><td>7</td></tr></table>"
    changed = "<table><tr><td>Milk</td><td>2</td></tr><tr><td>Bread</td><td>7</td></tr></table>"
    records = extract_blocks(clean_dom(before))
    assert not diff_blocks(records, extract_blocks(clean_dom(reordered))).has_changes
    assert diff_blocks(records, extract_blocks(clean_dom(changed))).has_changes


def test_noise_removal_preserves_entities_and_links() -> None:
    html = (
        "<main><script>random()</script><!-- churn --><p>A &amp; B</p>"
        "<a href='/stock'>Stock</a></main>"
    )
    cleaned = clean_dom(html, base_url="https://example.com/shop/")
    assert "random" not in cleaned and "churn" not in cleaned
    blocks = extract_blocks(cleaned)
    assert any(block.text == "A & B" for block in blocks)
    assert any("https://example.com/stock" in block.text for block in blocks)
