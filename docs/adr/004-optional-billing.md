# ADR 004: optional billing behind a provider boundary

Status: accepted

## Problem

The same code serves a single self-hosted owner and a hosted, multi-tenant deployment. Organizations already have plans with site, member and AI-check limits. A hosted deployment also needs those limits to follow a paid subscription, while a self-hosted owner should never meet a payment flow, a provider account or a legal gate.

Payment events arrive asynchronously, can be replayed or reordered, and are the only evidence of what a tenant paid for. Deriving access from them carelessly either gives away paid limits or locks out a paying tenant.

## Decision

Billing is a separate module (`src/driftwatch/billing`) that is off by default (`DRIFTWATCH_BILLING_PROVIDER=disabled`). With it off, the operator manages plans and limits, the Billing page shows the organization's plan with purchases closed, the checkout, portal and webhook endpoints refuse requests, and no provider is called. Monitoring never depends on it.

The service talks to a provider protocol; Stripe is the only adapter. Provider configuration, self-serve checkout, the legal gate (versioned Terms and Privacy with their SHA-256 digests) and live mode are independent switches, and configuration validation rejects combinations that are not safe, such as public registration together with self-serve checkout.

Webhooks are verified on the raw body before any parsing, stored in an append-only event ledger and deduplicated by provider event ID. Processing is claimed atomically, so a replay or a concurrent delivery projects an event at most once, and reconciliation reads the provider's full subscription list to close stale local state. Access is a projection: only recognized, unexpired entitled states grant a plan, and every unknown or incomplete state fails closed. A billing suspension is kept apart from an operator's manual suspension, so a later payment cannot reactivate a tenant the operator disabled.

## Alternatives and consequences

- Leaving billing out would keep the code smaller, but plans would then have no path to paid limits, and a hosted deployment would need a fork.
- Calling the provider's API on each request instead of projecting events would make access depend on the provider's availability and rate limits.
- A provider-agnostic boundary costs an extra layer for one adapter. It keeps Stripe's payload shapes out of the service and lets tests run against a recorded transport.

The billing tables exist in every database, including those where billing stays disabled. The module is the largest optional part of the code base and adds review cost on each change to plans or organizations.

## Verification

`tests/test_billing_provider.py` checks webhook signatures, tolerance and payload normalization against a mock transport. `tests/test_billing_service.py` and `tests/test_billing_api.py` cover projection, replay, out-of-order events and checkout idempotency, and `tests/test_config.py` covers the configuration gates. `tests/test_postgres_integration.py` runs the concurrent event processing and the append-only ledger on PostgreSQL. See [Architecture](../ARCHITECTURE.md#billing-and-entitlements) for the data model.
