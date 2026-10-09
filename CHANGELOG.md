# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Public portfolio license

- Publish the project under PolyForm Noncommercial 1.0.0. Allow noncommercial
  use, modification and redistribution under its terms; commercial use requires
  separate written permission. Align package metadata and contributor guidance,
  and preserve the independent licenses of third-party components.

### Maintainability

- Make the regression test directory an explicit Python package so shared test
  fixtures resolve when running the `pytest` console command on a fresh checkout.
- Split the settings page into configuration domains, account controls,
  operations and usage views, with a shared local draft and pure payload model.
  Preserve step-up, unsaved-change protection and one-time MFA recovery behavior.
- Move query hooks into domain modules behind the existing public import facade;
  share session/cache boundaries, context guards and sensitive mutation handling.
- Apply Ruff to the whole repository in CI and contributor checks. Clean up
  historical migration annotations, imports and formatting without changing
  migration operations or their revision chain.

### Self-hosted portfolio setup

- Let the first successful signup on a fresh instance become its operator and
  default-organization administrator. Claim the setup transactionally and keep
  it closed after restarts or account deletion; preserve existing users on upgrade.
  Separate this from ongoing public signup and retain an explicit seeded-owner option.
- Allow the first owner to manage their home organization through administrator
  membership while preserving MFA and audited support access to other organizations.
- Improve text contrast over generated artwork and use locally served body and
  display fonts with upstream source records and licenses.
- Give onboarding, operations and standalone settings/plan notices opaque
  reading surfaces and clearer borders; highlight the current setup step without
  allowing decorative artwork to show through the copy.
- Commit first-owner registration and MFA enrollment before issuing successful
  responses or sessions. Keep one-time recovery codes visible through the first
  enrollment transition until the owner confirms they have saved them.
- Finish every request-scoped database transaction before sending the HTTP
  response. Roll back failed commits, keep session changes durable before cookies
  reach the browser, and remove temporary backup files when audit persistence fails.
- Interpret timezone-free SQLite API timestamps as UTC and synchronize language
  changes before formatting dates, including activity near local midnight.
- Clarify the README's self-hosted purpose, first-run instructions, public source
  checklist and optional modules; remove an unsupported security-response promise.

### Monitoring, recovery and publication preparation

- Specify structured record comparison and add a deterministic offline demo
  with a semantic counterexample corpus. Reject empty captures and HTTP errors;
  retain the previous baseline and resolve document links from the captured base.
- Add explicit AI-disabled monitoring and analysis lifecycle/ownership, immutable
  model/rules/input provenance and nullable pricing. Reviewed agreement describes
  the reviewed sample; local usage estimates do not constitute a provider invoice.
- Fence account mail and notification completion, bound crash retries and protect
  unfinished analysis/delivery through retention. Password reset and pending TOTP
  consumption are atomic; interaction secrets are bound to their allowed origin.
- Correct tenant selection, grants, export scope, older-event links, partial
  bulk retries, mutation errors, dirty drafts and picker cancellation. Add strong
  keyboard focus and a localized recovery screen for route or deployment errors.
- Integrate the visual identity and responsive bitmap illustrations; replace
  historical screenshots with current views using synthetic data.
- Add hash-locked installation, independent generated deployment keys, redacted
  tree/history/staged secret scans and CI gates. Separate Chromium credentials
  from the API and provide a reference packet firewall and actual socket smoke.
- Document installation, FAQ, operational recovery, architecture decisions and
  the distinction between verified reference behavior and deployment checks.

### Added

- Opt-in linked-document watching (`watch_linked_documents`, org-overridable,
  off by default, with a toggle in the settings filters section): the check
  pipeline HEAD-probes document links (PDF/Word/Excel/ODT, up to 20 per site,
  SSRF-vetted, short timeout) and fingerprints ETag/Last-Modified/size, so a
  file replaced under the same URL raises a normal change
  ("[document] {url} updated") through the usual diff → AI → notification
  path. Probe failures are skipped silently.
- A site that keeps failing now escalates: the runner counts consecutive
  capture failures and, when the count crosses an org-overridable threshold
  (`site_down_failure_threshold`, default 5), sends one stronger localized
  "site appears down" alert that bypasses the normal 6-hour throttle exactly
  once. The underlying error message is stored on the site and shown in the
  alert badge tooltips on the dashboard and the site page.
- The site, project, and add-site rule editors show a collapsed read-only
  "Currently effective rules" panel with a source badge (site / project /
  global / default), backed by `GET /api/sites/{id}/effective-rules`,
  `GET /api/projects/{id}/effective-rules`, and `GET /api/sites/effective-rules`
  for a not-yet-created site.
- Re-analyzing a change no longer erases what the previous analysis said:
  every successful analysis is appended to a new `analysis_runs` history
  table, exposed in the change detail API, and the change view shows a
  collapsed "Previous verdicts" disclosure.
- Rules dry-run: `POST /api/changes/{id}/analyze-preview` tests draft
  importance rules against a past change and returns a preview without replacing
  the stored verdict; quota and usage are recorded. The site/project rules editors grew a
  "Test rules on this change" button rendering the preview inline. The
  dry-run bills the model, records usage, and respects the monthly AI quota.
- Human feedback on AI verdicts: an agree/disagree toggle next to the
  significance badge stores a reviewer's verdict beside (never over) the AI's
  own, via `POST /api/changes/{id}/verdict`, and
  `GET /api/usage/verdicts` rolls up per-site agreement rates with the
  overrides split into false positives and false negatives.

- Notification emails, webhooks, and the dashboard's recent-changes list now
  deep-link to the exact change (`/sites/{id}?change={id}`), and signing in
  returns you to the link you followed instead of the dashboard.
- A change that resolves no recipients (and has no webhook) now writes a
  `skipped` row to the notifications audit log instead of vanishing silently,
  skips the AI analysis spend entirely, and the site page warns when neither
  the site nor its project has recipients.
- The change view shows a per-change "Deliveries" list (recipient, status,
  error), backed by a `change_id` filter on `GET /api/notifications`.
- Scheduled SQLite backups: the scheduler snapshots the database into
  `data_dir/backups/` every `DRIFTWATCH_BACKUP_INTERVAL_HOURS` (default 24,
  0 disables), keeps the newest `DRIFTWATCH_BACKUP_KEEP_COUNT` (default 7),
  caps the pre-restore safety copies with the same retention, and reports
  backup status in authenticated Operations. SQLite-only; Postgres
  deployments keep using provider backups.
- Authenticated Operations reports SQLite storage metrics: `db_bytes`,
  `wal_bytes`, and `disk_free_bytes` (all null on Postgres). Public `/healthz`
  provides minimal readiness; it does not expose backup paths or storage details.
- Dashboard site cards show a rose "Alert" badge (with an explanatory tooltip)
  when the site's last capture left an operational alert, so a dying site is
  visible without opening its detail page.

## [1.0.0] - 2026-07-04

Initial implementation.

### Added

- **Monitoring pipeline** — pages are rendered in a real browser (Playwright),
  stripped of chrome and volatile tokens, reduced to comparable content blocks,
  and compared against the last snapshot under a documented record policy.
  Configured volatile regions are ignored; meaningful field associations remain.
- **AI significance classification** — each change is judged by an OpenAI model
  against operator-written importance rules, with a headline and summary in the
  page's language; failed analyses are retried with backoff instead of being
  dropped.
- **Notifications** — per-recipient email (SMTP or Brevo) and webhooks (generic
  JSON, Slack, Discord), an org-overridable email language (English/Polish),
  subject templates, holiday-cover substitutions resolved at send time, and an
  audit log of every delivery.
- **Multi-tenancy** — organizations as isolated workspaces with a fail-closed
  ORM scope filter, a layered settings store (org override else instance
  default, secrets encrypted at rest), per-org white-label branding, and an
  operator-managed plan catalog with server-enforced site and AI-check limits.
- **Accounts and security** — Argon2 passwords, stateless JWT session cookies,
  TOTP two-factor auth with recovery codes, step-up re-authentication for
  destructive actions, self-service password reset, login throttling, a CSRF
  origin guard, and SSRF protection on captures and webhooks.
- **Visual picker** — point-and-click selection of the page region to watch,
  with recordable click/type steps for pages behind logins or banners.
- **Web app** — React + TypeScript SPA: dashboard, diff viewer, projects,
  recipients, access control, settings with test email/webhook, XLSX export
  (localized), log viewer, SQLite backup/restore, switchable themes, English
  and Polish UI.
- **Operations** — single Docker image, Alembic migrations applied on startup,
  health check endpoint, deploy guides for Docker Compose and Railway +
  Supabase.
