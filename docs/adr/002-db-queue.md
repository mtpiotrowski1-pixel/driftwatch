# ADR 002: durable work in the application database

Status: implemented. Scope: site checks, analysis ownership and notification delivery.

## Context

A monitor can overlap a scheduled tick, a manual check, a slow provider and a
process restart. An in-memory task list loses work on restart. Holding a database
transaction open across Chromium or email calls blocks unrelated requests and
cannot atomically commit a third-party side effect.

## Decision

Use a database queue rather than add a separate broker for this deployment size.
Enqueue and reserve capacity transactionally. Claim eligible work with a random
lease token, an expiry and an attempt budget. Renew and finish through conditional
updates that require the current token and a live lease. Network work takes place
outside long database transactions. An old owner may complete its network call,
but cannot overwrite the result after losing the lease.

Checks have one active marker per site, bounded global/per-organization admission
and a maximum attempt count. Expired process-crash claims consume that budget:
reclaim marks exhausted work dead before it selects another attempt. Operators
can review a dead job and create an audited, idempotent redrive rather than
silently reset its evidence.

Delivery has one durable row per change/recipient/channel. A dispatcher obtains
a fresh clock reading for each claim and completion, so a slow batch cannot give
later recipients leases that are already expired. Provider calls are bounded by
the remaining lease budget. The token and expiry fence the completion update.

Analysis owns a separate lease and has explicit pending/processing/succeeded,
error/quota-blocked and deliberately skipped states. Retention keeps unresolved
analysis, leased work, retry/action-required state and undelivered notification
evidence together with the referenced old/new snapshots. A pending result is
not treated as a completed insignificant verdict.

## Guarantees and tradeoffs

This provides crash recovery and prevents stale database writes; it cannot
promise exactly-once provider delivery. If SMTP accepts a message and the
process dies before recording success, a later attempt can send it again. A
stable message identifier helps trace that case but is not a provider deduplication
contract. Billing adapters have their own idempotency rules.

SQLite is convenient for a single small instance and serializes writes. PostgreSQL
supports stronger concurrent deployment checks. The reference topology still uses
one API/scheduler replica: passing local concurrency tests is not proof that an
arbitrary replica count is safe or fast. Queue tables must be monitored and pruned;
long outages can preserve more history than the nominal retention setting.

Introduce a broker only when measured throughput, independent worker scaling or
operational isolation justifies its extra state and delivery contracts. Changing
the transport must preserve the existing ownership and recovery semantics.

## Evidence

`tests/test_reliability_regressions.py` exercises controlled clock progression,
slow batches, stolen tokens, deadline cancellation, process-crash exhaustion,
incomplete provider configuration and retention. `tests/test_check_queue.py` and
`tests/test_postgres_integration.py` cover queue/concurrency behavior. These tests
use controlled providers; an SMTP acceptance/crash ambiguity remains by design.
