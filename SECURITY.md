# Security Policy

## Supported versions

Security fixes target the current maintained source revision. This portfolio
project does not provide a response-time or support guarantee for hosted instances.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Use GitHub's private vulnerability reporting ("Security" tab → "Report a
vulnerability"). If it is not available, contact the maintainer through GitHub
and ask for a private channel before sharing details. Include the affected
revision, endpoint or component, reproduction steps and impact.

Please allow a reasonable window for a fix before publishing details. Credit is
given in the advisory unless you prefer otherwise.

## Scope notes for operators

- Public deployments require distinct `DRIFTWATCH_SESSION_SECRET_KEY` and
  `DRIFTWATCH_ENCRYPTION_KEY` values. Previous-key rings support bounded
  rotation; the compatibility `DRIFTWATCH_SECRET_KEY` fallback is not accepted
  in production.
- Public registration is closed by default. Keep it closed unless email
  verification, edge abuse controls, legal documents, and the intended tenant
  lifecycle have been reviewed. Creating users from the admin panel sends a
  one-time setup invitation; administrators do not choose or receive customer
  passwords.
- One-time first-account setup is separate from ongoing public registration.
  It gives the first successful registration administrator/operator privileges
  only on a fresh instance. Local setup is allowed by default; a non-loopback
  runtime requires explicit initial-signup configuration or a seeded account.
  Complete owner setup before exposing the instance. A durable database marker
  prevents account deletion or a restart from reopening first-owner registration;
  existing users are not promoted by an upgrade.
- Every session and purpose-scoped token is bound to both `token_version` and a
  random `session_generation`. Password/account security changes revoke the
  former; a SQLite database restore rotates the latter for every user so a token
  issued before the backup or restore cannot become valid again.
- Secrets configured in the app (OpenAI key, SMTP password, webhook URL, TOTP
  seeds, and interaction values) are encrypted at rest and masked or omitted
  from API responses. Database backups still contain encrypted secret material
  and must be protected together with the encryption-key lifecycle.
- Public page capture runs in the separate `capture-worker` image. The worker
  receives its own capture-service token and ephemeral plaintext fill values
  for an approved origin per request. It receives no application database, AI,
  mail, billing, session-signing or encryption credentials. The API
  refuses in-process capture on a public deployment unless an explicit unsafe
  compatibility switch is enabled.
- Logical HTTP/SMTP clients validate every hop and connect to a vetted address.
  Chromium pins the initial navigation host and revalidates every redirect,
  subresource and WebSocket, but browser-discovered hosts retain a residual
  DNS resolve-to-connect window outside application control. Production
  therefore requires packet filtering. Reference Compose provides a dedicated
  firewall network namespace for the worker: only that credential-free sidecar
  has `NET_ADMIN`; Chromium remains non-root, read-only and cap-drop ALL. It
  rejects private, CGNAT, loopback and link-local/metadata connections and disables
  IPv6 egress. Docker's embedded DNS address is a narrowly documented exception.
  Other hosting platforms must provide the equivalent boundary. The API/scheduler
  has a different trust domain and needs its own host egress policy, which the
  reference Compose file does not provide. That policy should deny private,
  link-local, metadata, multicast and loopback networks except for narrowly
  scoped database and capture-worker destination-and-port rules.
- Support access by the instance operator to another organization is locked by
  default on a public deployment. The first owner can administer their home
  organization through its server-verified administrator membership; this does
  not bypass MFA or provide access to another organization. Support reads and
  writes require MFA-backed step-up and a
  short-lived, organization-bound grant with an audited reason. The database
  record is authoritative, so expiry or revocation also blocks a copied grant
  cookie; grant, revoke, and every allowed request are appended to the ledger.
  Instance audit exposes only control-plane events; tenant events stay behind
  the entered organization and the same support grant.
- Restore and branding uploads are bounded, streamed raw bodies. Authentication
  and authorization run before body consumption, which avoids pre-auth multipart
  parsing as a denial-of-service surface. Branding accepts validated bitmap
  content into same-origin storage; legacy remote asset URLs are not rendered.
- Permanent organization deletion is disabled through the product API. Suspend
  an organization to stop work while retaining billing and audit evidence, then
  use an approved offboarding/DSAR process for export, provider cleanup,
  retention, and backup tombstones.
- Stripe support is fail-closed and disabled by default. Provider setup, public
  registration, self-serve checkout, the legal gate, and live mode are separate
  switches. Checkout consent is bound to versioned HTTPS Terms/Privacy artifacts
  and their SHA-256 digests. Before live payments, complete the
  [deployment verification](docs/DEPLOY.md#deployment-verification) and review
  the provider configuration.
- Public health JSON exposes status, routing readiness and coarse dependency
  states; a capture outage may return HTTP 200 with `status=degraded`.
  Detailed database, scheduler, worker, queue, storage, and maintenance state is
  available only to the instance operator through the authenticated Operations
  API.

Hardening guidance for deployments is in [docs/DEPLOY.md](docs/DEPLOY.md).
[docs/IMAGE_SECURITY.md](docs/IMAGE_SECURITY.md) documents the native package
locks, the two upstream backports and the image vulnerability gate, which also
fails on HIGH and CRITICAL findings that the vendor has not fixed yet.

## Secret scanning

`python scripts/secret_scan.py` downloads Gitleaks 8.30.1 from its official
release, verifies it against a committed SHA-256 checksum, and scans the Git
history of all local refs together with every tracked or unignored file. A
finding is reported as path, rule, line and commit; the secret value is never
printed. The exit code is 1 for findings and 2 for an incomplete scan, for
example on a shallow clone. `--staged` checks only staged changes and is the
mode used by the pre-commit hook. CI runs the full scan with complete history.

Accepted test values are listed in `.gitleaks.toml` as exact value and path
pairs. Inline `gitleaks:allow` markers and `.gitleaksignore` files are
rejected, and an ambient Gitleaks configuration cannot override the policy.

If a real credential was committed, rotate it with the provider first. Removing
the line does not remove it from Git history; see [GitHub's guidance on removing
sensitive data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).
