"""Prompt assembly for change analysis.

The model always receives a fixed *base* instruction (what to judge and how to
shape the answer) joined with one *importance ruleset* chosen by inheritance:
a site's own rules win, else its project's, else the global rules, else the
built-in default. The base instruction is never overridden, so the structured
contract holds regardless of how a user phrases their rules.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BASE_PROMPT = (
    "You decide whether a change to a watched web page matters to the people "
    "following it. Judge only against the importance rules in the next section. "
    "Write the headline and summary in the same language as the page content. "
    "When the change is not significant, still say briefly what changed and why "
    "it does not matter."
)

DEFAULT_IMPORTANCE_RULES = (
    "Significant: new or changed prices, product or service availability, "
    "official announcements, new or updated articles and documents (including "
    "linked PDFs), changed dates, deadlines, opening hours, or contact details.\n\n"
    "Not significant: purely visual or cosmetic edits, typo fixes, re-ordering, "
    "session identifiers, timestamps, dynamic tokens, advertising, and changes "
    "to navigation or footer that do not affect the main content."
)


@dataclass(frozen=True, slots=True)
class ResolvedRules:
    source: str  # "site" | "project" | "global" | "default"
    text: str


def resolve_importance_rules(
    *,
    site_prompt: str | None,
    project_prompt: str | None,
    global_rules: str | None,
) -> ResolvedRules:
    if site_prompt and site_prompt.strip():
        return ResolvedRules("site", site_prompt.strip())
    if project_prompt and project_prompt.strip():
        return ResolvedRules("project", project_prompt.strip())
    if global_rules and global_rules.strip():
        return ResolvedRules("global", global_rules.strip())
    return ResolvedRules("default", DEFAULT_IMPORTANCE_RULES)


def build_system_prompt(rules: ResolvedRules, *, base_prompt: str | None = None) -> str:
    base = (base_prompt or DEFAULT_BASE_PROMPT).strip()
    return f"{base}\n\nImportance rules (source: {rules.source}):\n{rules.text}"
