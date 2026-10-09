# Preparing a public portfolio repository

Driftwatch is shared as a self-hosted portfolio project. Publishing its source
does not require publishing a running service, enabling public signup or
configuring billing. The default monitoring path works without paid AI.

## What belongs in the repository

- Source, migrations, exact dependency locks, CI and installation scripts.
- [PolyForm Noncommercial 1.0.0](../LICENSE), preserved
  [third-party notices](../THIRD_PARTY_NOTICES.md) and font licenses. Publicly
  available source does not grant commercial use and is not OSI open source.
- Architecture decisions, monitoring semantics, tests and honest limitations.
- Synthetic examples and screenshots, with their [capture manifest](screenshots/manifest.json).
- Generated artwork, original prompts and export provenance in the [brand kit](../brand-kit/README.pl.md).

Do not publish runtime `.env`, real provider credentials, cookies, invitation or
reset links, databases, snapshots, logs, backups or private working notes.
`.env.example` contains configuration examples, not deployable credentials.
The fixed PostgreSQL credentials in Compose/CI belong only to isolated test
environments. Do not reuse them for a hosted instance.

## Before the first public push

1. Review the exact outgoing source tree and every Git ref being published.
   `.gitignore` does not remove files already tracked or secrets in old commits.
2. Run `python scripts/secret_scan.py --history --files` from a complete checkout.
   A redacted clean report is a review aid, not proof that no secret can exist.
   Rotate a real exposed credential before publication and follow
   [the security policy](../SECURITY.md) for history repair.
3. Run the checks in [CONTRIBUTING](../CONTRIBUTING.md), including the owned browser
   fixtures and Docker smoke for a release using the reference containers.
   CI covers locked installs, Python on Windows/Linux, frontend checks,
   PostgreSQL, image advisories and real packet-boundary assertions.
4. Verify fresh first-account registration and a baseline/change on an owned page.
   Reuse an existing database to confirm the upgrade preserves users and data.
5. Keep scanner reports tied to source revision, image digest, advisory database
   date and scope. A result for an older image is not a scan of a new build.
6. Check the rendered README, relative links, screenshots and font/artwork
   provenance. Keep demo results visibly synthetic; do not present them as
   provider integration, uptime, model accuracy or compliance evidence.
7. Enable private vulnerability reporting in the new GitHub repository and
   inspect the first actual CI run. A workflow file is not a successful remote
   run. Use a repository description such as “Self-hosted web change monitoring
   with optional AI, durable jobs and isolated browser capture.”

The optional billing and multi-organization modules are retained because they
have their own boundaries and tests. They remain disabled for ordinary
self-hosted use. Deployment-specific legal and operations templates are
operator worksheets, not certifications or required portfolio setup.

## If you also publish a running demo

Use synthetic data, a separate database and keys, and a reviewed ingress policy.
Complete first-owner setup before exposing the host. Do not share an unclaimed
setup screen or your personal monitoring database. Follow [DEPLOY](DEPLOY.md),
[recovery](RECOVERY.md) and [SECURITY](../SECURITY.md); publishing code alone does
not validate backups, provider delivery, public traffic or another host's egress
boundary.
