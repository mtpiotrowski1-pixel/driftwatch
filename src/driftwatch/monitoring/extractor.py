"""Extract records while preserving the relationships within them.

Rows, cards, definitions and list items are atomic records. Whole independent
records may move without changing meaning; a value moving between two records
is a change. Ordered lists keep their item order. Standalone paragraphs remain
independent, matching the established paragraph-reordering policy. Short text
and div/span components are content too, including a single-digit price.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

_BLOCK_TAGS = {
    **dict.fromkeys(("h1", "h2", "h3", "h4", "h5", "h6"), "heading"),
    "p": "paragraph",
    "li": "list-item",
    "blockquote": "quote",
    "figcaption": "caption",
}
_RECORD_CONTAINERS = frozenset({"div", "article", "section"})
_GROUP_BOUNDARIES = frozenset({"table", "ul", "ol", "dl"})
_WHITESPACE = re.compile(r"\s+")
_TRACKING_QUERY_KEYS = frozenset({"fbclid", "gclid", "msclkid", "yclid"})


@dataclass(frozen=True, slots=True)
class ContentBlock:
    kind: str
    tag: str
    text: str
    context: tuple[str, ...] = ()

    def render(self) -> str:
        context = (
            self.context[:-1] if self.context and self.context[-1] == self.text else self.context
        )
        return f"[{self.kind}] {' / '.join((*context, self.text))}"


@dataclass(frozen=True, slots=True)
class BlockDiff:
    added: list[ContentBlock]
    removed: list[ContentBlock]

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed)


def extract_blocks(html: str) -> list[ContentBlock]:
    if not html or not html.strip():
        return []
    soup = BeautifulSoup(html, "html.parser")
    blocks: list[ContentBlock] = []
    _walk(soup.body or soup, blocks)
    return blocks


def _walk(element: Tag, blocks: list[ContentBlock], context: tuple[str, ...] = ()) -> None:
    if element.name == "tr":
        cells = element.find_all(("td", "th"), recursive=False)
        _append(
            blocks,
            "table-row",
            element.name,
            " | ".join(_field_text(cell) for cell in cells),
            context=context,
        )
        _links(element, blocks)
        return
    if element.name == "ol":
        # Comparing this complete record preserves order, including duplicate
        # labels. An ordered procedure must not behave like an unordered menu.
        items = element.find_all("li", recursive=False)
        _append(
            blocks,
            "ordered-list",
            element.name,
            " | ".join(f"{index}. {_field_text(item)}" for index, item in enumerate(items, 1)),
            context=context,
        )
        _links(element, blocks)
        return
    if element.name == "dl":
        term: list[str] = []
        definitions: list[str] = []
        for entry in element.find_all(("dt", "dd"), recursive=False):
            if entry.name == "dt" and definitions:
                _append(
                    blocks, "definition", "dl", " | ".join([*term, *definitions]), context=context
                )
                term, definitions = [], []
            (term if entry.name == "dt" else definitions).append(_field_text(entry))
        _append(blocks, "definition", "dl", " | ".join([*term, *definitions]), context=context)
        _links(element, blocks)
        return
    if element.name == "a":
        _append(blocks, "link", "a", _link_text(element), context=context)
        return
    if element.name in _BLOCK_TAGS:
        _append(blocks, _BLOCK_TAGS[element.name], element.name, _text(element), context=context)
        _links(element, blocks)
        return
    if element.name in _RECORD_CONTAINERS and not element.find(_GROUP_BOUNDARIES):
        _append(blocks, "record", element.name, _text(element), context=context)
        _links(element, blocks)
        return

    # Inline children and bare text form one run. Block boundaries flush that
    # run, avoiding both missed text and duplicate extraction of descendants.
    child_context = context
    if element.name in {*_RECORD_CONTAINERS, "table"}:
        scope = _scope_text(element)
        if scope:
            child_context = (*context, scope)
    pending: list[str] = []
    for child in element.children:
        if isinstance(child, NavigableString):
            pending.append(str(child))
        elif isinstance(child, Tag):
            if child.name in {"span", "b", "strong", "i", "em", "small", "code", "time"}:
                pending.append(_text(child))
                _links(child, blocks)
            else:
                _append(blocks, "text", element.name, " ".join(pending), context=child_context)
                pending = []
                _walk(child, blocks, child_context)
    _append(blocks, "text", element.name, " ".join(pending), context=child_context)


def _scope_text(element: Tag) -> str:
    """Keep an owning section's labels when its table/list records are split."""
    parts = [
        str(child) if isinstance(child, NavigableString) else _text(child)
        for child in element.children
        if isinstance(child, NavigableString)
        or (isinstance(child, Tag) and child.name in {*_BLOCK_TAGS, "span", "caption"})
    ]
    return _WHITESPACE.sub(" ", " ".join(parts)).strip()


def _append(
    blocks: list[ContentBlock], kind: str, tag: str, text: str, *, context: tuple[str, ...] = ()
) -> None:
    text = _WHITESPACE.sub(" ", text).strip()
    if text:
        blocks.append(ContentBlock(kind=kind, tag=tag, text=text, context=context))


def _text(element: Tag) -> str:
    parts: list[str] = []
    for child in element.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag):
            parts.append(_link_text(child) if child.name == "a" else _text(child))
    return _WHITESPACE.sub(" ", " ".join(parts)).strip()


def _field_text(element: Tag) -> str:
    # Preserve cell/item boundaries even when page text contains our delimiter.
    return _text(element).replace("\\", "\\\\").replace("|", "\\|")


def _link_text(element: Tag) -> str:
    text = _WHITESPACE.sub(" ", element.get_text(" ", strip=True)).strip()
    href = _normalise_href(element.get("href"))
    return f"{text} [{href}]" if text and href else href or text


def _links(element: Tag, blocks: list[ContentBlock]) -> None:
    # Keep a separate link index for the optional linked-document checker. The
    # owning record also contains each href, so label/value association survives.
    for anchor in element.find_all("a"):
        _append(blocks, "link", "a", _link_text(anchor))


def canonical_text(blocks: list[ContentBlock]) -> str:
    """One line per semantic record, used for storage and display."""
    return "\n".join(block.render() for block in blocks)


def diff_blocks(old: list[ContentBlock], new: list[ContentBlock]) -> BlockDiff:
    """Compare complete record identities; independent record order is ignored."""
    old_counts = Counter((block.kind, block.text, block.context) for block in old)
    new_counts = Counter((block.kind, block.text, block.context) for block in new)
    return BlockDiff(added=_surplus(new, old_counts), removed=_surplus(old, new_counts))


def _surplus(
    blocks: list[ContentBlock], other_counts: Counter[tuple[str, str, tuple[str, ...]]]
) -> list[ContentBlock]:
    seen: Counter[tuple[str, str, tuple[str, ...]]] = Counter()
    surplus: list[ContentBlock] = []
    for block in blocks:
        key = (block.kind, block.text, block.context)
        seen[key] += 1
        if seen[key] > other_counts.get(key, 0):
            surplus.append(block)
    return surplus


def format_for_ai(diff: BlockDiff) -> str:
    lines: list[str] = []
    if diff.added:
        lines.append("ADDED:")
        lines.extend(f"  + {block.render()}" for block in diff.added)
    if diff.removed:
        if lines:
            lines.append("")
        lines.append("REMOVED:")
        lines.extend(f"  - {block.render()}" for block in diff.removed)
    return "\n".join(lines)


def _normalise_href(href: object) -> str:
    if not isinstance(href, str) or not href.strip():
        return ""
    href = unescape(href).strip()
    if href.startswith("#") or href.lower().startswith(("javascript:", "mailto:", "tel:")):
        return ""
    parts = urlsplit(href)
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
