"""Canonical analysis input shared by provenance and the provider adapter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

_TRUNCATION_MARKER = "\n\n[... diff truncated ...]"


@dataclass(frozen=True, slots=True)
class AnalysisInput:
    diff_text: str
    sha256: str
    truncated: bool


def user_message(url: str, diff_text: str) -> str:
    # A page must not be able to close the data block early and continue with text
    # that reads like instructions.
    contained = diff_text.replace("</page_changes", "<\\/page_changes")
    return f"URL: {url}\n\n<page_changes>\n{contained}\n</page_changes>"


def prepare_input(
    *, diff_text: str, url: str, system_prompt: str, model: str, max_chars: int
) -> AnalysisInput:
    if max_chars < len(_TRUNCATION_MARKER):
        raise ValueError("Analysis input limit is smaller than the truncation marker")
    truncated = len(diff_text) > max_chars
    if truncated:
        diff_text = diff_text[: max_chars - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER
    # Versioned, unambiguous serialization covers exactly the two messages and
    # requested model, rather than only the uncapped raw diff.
    encoded = json.dumps(
        {
            "version": 2,
            "model": model,
            "system": system_prompt,
            "user": user_message(url, diff_text),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return AnalysisInput(diff_text, hashlib.sha256(encoded).hexdigest(), truncated)
