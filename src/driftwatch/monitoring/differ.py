"""Render line-level diffs of canonical content text.

The unified text form feeds the AI and the XLSX export; the HTML form drives
the in-app diff viewer. Page content is attacker-controlled, so every line is
HTML-escaped before it reaches the markup.
"""

from __future__ import annotations

import difflib
from html import escape

MAX_HTML_DIFF_CHARS = 200_000


def unified_text_diff(old: str, new: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile="previous",
        tofile="current",
        lineterm="",
    )
    return "\n".join(diff)


def html_diff(old: str, new: str) -> str:
    """An escaped, line-classified diff: ``added`` / ``removed`` / ``context``."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    # Keep the standard popularity heuristic: repetitive large pages otherwise
    # make matching quadratic. Domain detection compares records separately.
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines)
    rows: list[str] = []
    # Bound context around each actual change. Rendering the entire unchanged
    # page first used to consume the display limit before a late change appeared.
    for group in matcher.get_grouped_opcodes(n=3):
        if rows:
            rows.append('<div class="diff-line diff-context">…</div>')
        for tag, i1, i2, j1, j2 in group:
            if tag in ("replace", "delete"):
                rows.extend(_row("removed", line) for line in old_lines[i1:i2])
            if tag in ("replace", "insert"):
                rows.extend(_row("added", line) for line in new_lines[j1:j2])
            if tag == "equal":
                rows.extend(_row("context", line) for line in old_lines[i1:i2])

    markup = f'<div class="diff">{"".join(rows)}</div>'
    if len(markup) > MAX_HTML_DIFF_CHARS:
        return _truncate(rows)
    return markup


def _row(kind: str, line: str) -> str:
    return f'<div class="diff-line diff-{kind}">{escape(line) or "&nbsp;"}</div>'


def _truncate(rows: list[str]) -> str:
    # If changes alone exceed the limit, omit context before omitting any change.
    rows = [row for row in rows if 'class="diff-line diff-context"' not in row]
    kept: list[str] = []
    size = 0
    notice = '<div class="diff-line diff-truncated">Diff truncated — too large to display.</div>'
    budget = MAX_HTML_DIFF_CHARS - len(notice) - len('<div class="diff"></div>')
    for row in rows:
        if size + len(row) > budget:
            # Even one huge changed line must have visible evidence. Escape is
            # already applied; clip before an incomplete character reference.
            available = budget - size
            if available > 150:
                prefix, _, text = row.partition(">")
                clipped = text[: available - len(prefix) - len(">…</div>")]
                if "&" in clipped and clipped.rfind("&") > clipped.rfind(";"):
                    clipped = clipped[: clipped.rfind("&")]
                kept.append(f"{prefix}>{clipped}…</div>")
            break
        kept.append(row)
        size += len(row)
    return f'<div class="diff">{"".join(kept)}{notice}</div>'
