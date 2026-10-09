# What counts as a website change

Driftwatch compares records extracted from the rendered HTML. AI classifies an already detected change; it does not decide whether the page changed. Monitoring with AI disabled uses the same detection path and delivers all detected changes.

The machine-readable examples in [`tests/fixtures/monitoring_cases.json`](../tests/fixtures/monitoring_cases.json) state the expected result independently of the extraction implementation. Both helper-level and database-pipeline tests run each example.

## Capture and cleaning

The browser waits for `domcontentloaded`, replays the configured interactions and waits for the request's settling interval. A selected element is captured with its outer HTML, retaining a selected `span`, paragraph, list item or row. The capture also carries `document.baseURI`, so relative document links resolve using the final document and its `<base>` element rather than the originally watched URL. Resolved links are stored in snapshot HTML.

An HTTP error response is a failed capture, including an error reached through an interaction. It never replaces a healthy baseline. HTTP 5xx, 408 and 429 failures are retryable; other HTTP errors require correction. Missing selectors and blocked navigation fail explicitly. Content over the capture limit fails instead of silently accepting an incomplete snapshot.

Cleaning removes configured ignored regions, comments, non-content elements such as scripts/navigation/forms, and explicitly volatile attributes such as `nonce` or `data-request-id`. It preserves visible numbers, dates, UUIDs and document identities. A 13-digit order number cannot safely be inferred to be a timestamp. Use an ignore selector for a visible clock or genuinely noisy region.

Links retain their path and identity parameters. `utm_*`, `fbclid`, `gclid`, `msclkid` and `yclid` tracking parameters are removed. Arbitrary `t`, `timestamp`, `session` or similar keys are preserved because the application cannot prove they are semantically irrelevant.

## Records and relationships

| HTML/content | Comparison policy |
| --- | --- |
| Standalone paragraph, heading or bare text | Keep all non-empty text, including a single digit. Independent records can move. |
| `div`, `article`, `section` without descendant tables/lists/definitions | Keep the complete container as one record, including nested fields. Field order inside the record remains meaningful. |
| Table row | Keep cells together and preserve their order and boundaries. Whole rows can move within the same context. |
| Unordered-list item | Keep each complete item together; whole items can move. |
| Ordered list | Keep the complete ordered sequence. Reordering a procedure is a change. |
| Definition list | Keep the term with its definitions. |
| Table/list inside a labelled section or a captioned table | Retain the owning labels/caption as record context. Values from different sections cannot cancel each other. |
| Link | Keep the label and normalized destination; retain a link index for optional document fingerprint probes. |

Comparison uses the record kind, complete content and owning context, including duplicate counts. It does not compare a global bag of isolated values.

For example, `Basic: 10, Pro: 20` changing to `Basic: 20, Pro: 10` is a change even though the same names and prices remain on the page. Moving complete Basic and Pro records leaves their associations intact. The corpus covers both cases, nested card fields, labelled lists, captioned tables, short prices, identifiers, ordered lists, tracking noise and explicit ignored regions.

Generic HTML is ambiguous. A container may be a card or an entire grid; there is no universal proof that all children can be reordered freely. Driftwatch conservatively retains order inside a generic record. Reordering cards within such a wrapper may therefore produce a change. Narrow the watched selector to meaningful content and use explicit exclusions for noise. This policy prefers an inspectable extra change over silently losing a business relationship.

## Display and linked documents

The display diff renders changed hunks with a few nearby lines, rather than spending the display limit on an unchanged prefix. If changed content itself exceeds the limit, the viewer shows a truncation notice and visible changed content. All page-derived lines are escaped.

Optional linked-document watching probes ETag, Last-Modified and Content-Length on document-looking links. A changed observed fingerprint creates a synthetic document change even when the page HTML is identical. A missing or unchanged fingerprint is not proof that the document bytes are identical; servers that expose no useful validators cannot provide this signal. Probe failures do not replace the page baseline.

Existing snapshots keep their original HTML. The current extractor recalculates both sides under the same semantics; the displayed old side uses that recalculated canonical text rather than stale text from an earlier extraction version.

## Verification

```sh
pytest -q tests/test_monitoring_semantics.py tests/test_monitoring_units.py tests/test_linked_assets.py
pytest -q tests/test_capture.py tests/test_capture_browser.py tests/test_capture_worker.py
```

The semantic corpus uses scripted capture to isolate domain behavior and a real SQLite persistence path. Browser tests separately exercise the actual rendering adapter against a controlled fixture. Neither a mock nor a passing corpus proves correct monitoring of every possible website: check the captured region and first real diff for each configured site.
