# ADR 001: compare records with their relationships

Status: accepted

## Problem

Comparing a multiset of isolated text values ignores reorder, but it also hides changes in relationships. A table that changes `Basic: 10, Pro: 20` to `Basic: 20, Pro: 10` contains the same words and numbers. A global text counter therefore reports no change. Filtering out short text and guessing that long numbers or UUIDs are noise creates further false negatives.

## Decision

Extract complete records and compare their kind, content and owning context, retaining duplicate counts. Rows keep their cells; cards keep their fields; definition terms keep their values. Ordered lists preserve order. Labelled sections and table captions remain context for their nested records. Links preserve business identity; only explicit tracking parameters are normalized.

Whole independent records, standalone paragraphs, complete table rows and unordered-list items may move without a change. Order inside a generic container remains significant. The cleaner removes explicit volatile attributes and configured ignored regions, without guessing that visible identifiers are noise. Capture preserves the selected wrapper and actual document base URL. Error pages and oversized captures fail without replacing the baseline.

The same extractor recalculates both old and new snapshot HTML. Display diffs prioritize actual changed hunks and escape page content. AI receives detected record changes and adds an importance verdict; it is optional for all-change monitoring.

## Alternatives and consequences

- Raw HTML diffs detect markup churn and make harmless layout changes noisy.
- A global text-value multiset is insensitive to reorder, but erases business associations.
- Site-specific semantic models could be more precise, but require maintained custom extractors for every page and are outside the current product contract.

Record comparison is a small general-purpose compromise. Generic HTML does not reliably declare which children are independent, so nested container reorder can be reported conservatively. Named context changes can also affect several related records. Users can choose a narrower selector and explicitly exclude noisy regions; the application must not silently hide plausible business changes to reduce alerts.

The independent expected-outcome corpus lives in `tests/fixtures/monitoring_cases.json` and runs through extraction and real database persistence. Real browser regressions cover capture boundaries separately. The exact supported semantics and limitations are documented in [Monitoring semantics](../MONITORING_SEMANTICS.md).
