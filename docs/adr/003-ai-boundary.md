# ADR 003: optional importance analysis with immutable provenance

Status: accepted

## Problem

A website monitor must establish changes without relying on a model's opinion.
Conflating “not significant,” model failure, missing credentials and disabled AI
would silently suppress useful evidence. Reconstructing old verdict inputs from
current settings would misrepresent why an earlier decision was made. Unknown
model prices and sparse human reviews also make convenient aggregate metrics
misleading if they are presented as zero cost or complete detection accuracy.

## Decision

Browser capture and deterministic record comparison create the event independently
of AI. The record semantics are specified in [ADR 001](001-record-diff.md) and
[Monitoring semantics](../MONITORING_SEMANTICS.md). AI classifies the importance
of an existing detected diff; it does not authorize capture or decide whether
the event exists.

Each site has `analysis_mode=ai|disabled`. Disabled analysis requires an explicit
`notification_mode=always`; inherited or only-significant delivery is rejected
because there is no importance verdict to filter on. This path makes no model
call, reserves no AI quota and retains inspectable diffs. Delivery still needs
a destination. Missing credentials with AI enabled are an error, never an
implicit switch to disabled analysis.

`analysis_status` separates pending, processing, succeeded, disabled,
not_requested, skipped_no_delivery, error and quota_blocked. A nullable
`significant` field cannot by itself convey these lifecycle distinctions.
Scheduled analysis is skipped when no effective recipient/webhook exists;
explicit analysis and previews remain intentional paid actions. Atomic
allowance reservation precedes the external call. Ownership tokens prevent a
late or competing completion from replacing the accepted result. Quota-blocked
events receive a retry time; failures use bounded backoff and ultimately require
an operator/editor action.

Every new completed `AnalysisRun` stores model, resolved rules source, rules
version, exact system prompt, input SHA-256, truncation flag and usage ID. The
hash covers the model input after the analysis input boundary, so it identifies
what was assessed rather than an uncropped browser page. Re-analysis appends a
run. Settings edits cannot rewrite old provenance. Legacy fields remain nullable
and the interface labels unknown values rather than inferring them from current
configuration. Input hashes support identity checks; they do not reproduce the
input or establish correctness.

Usage prices remain nullable. A known zero cost differs from a missing price.
Any unknown priced call makes the aggregate total unknown; the known subtotal
and unknown-call count remain available. There is no silent cheap-model fallback
for an unrecognized model. Recorded costs belong to their usage rows and are
estimates, not provider invoices.

The usage ledger covers accepted responses, previews and stale completions that
returned a valid verdict. Transport failures, refusals or malformed structured
responses may incur a provider charge without producing a usage row. Quota
reservation still counts such attempts. The local subtotal therefore cannot be
used as a complete provider bill, even when every recorded row has a known price.

Human reviews are stored alongside the AI significance label. The displayed
metric is **agreement on reviewed events** with an explicit reviewed denominator.
False-positive/negative counts describe importance-label disagreement within
that set. They do not establish missed-change detection or recall: undetected
changes have no event to label. Reviewing a verdict does not automatically
train or alter the model.

## Alternatives and consequences

- Asking AI whether an entire page changed makes basic monitoring depend on
  paid availability and an uncertain detector; the deterministic path remains
  independently testable instead.
- Treating missing credentials as disabled analysis can change notification
  behavior silently; the explicit mode validates its all-change policy.
- Copying current settings into historical display produces convenient but
  false provenance. Nullable legacy fields preserve the actual evidence gap.
- Displaying unknown prices as zero understates cost. Honest unknown totals
  require callers and charts to handle nulls.
- Calling reviewed agreement “accuracy” overclaims coverage. Controlled semantic
  fixtures and capture tests assess detection separately; production reviews
  assess importance decisions on the detected sample.

The stored prompt/provenance adds retention responsibility. It is tenant-scoped
and rendered as plain text; page-derived content does not execute in the viewer.
Explicit re-analysis/previews can consume quota even when ordinary delivery is
disabled by missing destinations, so the UI documents their side effects.

## Verification

The no-AI path, atomic limits/ownership, analysis input truncation, nullable prices
and historical provenance are covered by backend semantic/recovery/release
contract tests. Frontend tests verify legacy Unknown values, false truncation,
plain-text prompt rendering, unknown versus zero preview cost, reviewed
denominators and late results after draft/context changes. See
[administrator guide](../ADMIN_GUIDE.en.md) and [FAQ](../FAQ.md) for user-facing
behavior and operational limits.
