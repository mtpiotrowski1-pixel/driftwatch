# Backup, restore and unfinished work

## What must be preserved

Keep the database, uploaded branding assets, deployment configuration, encryption
key and previous encryption-key ring, plus the application revision/image digest.
Store encrypted backups away from the running disk and protect key recovery
separately. A database backup without its encryption key cannot restore saved
provider credentials or TOTP secrets. Do not publish backups or keys in Git.

SQLite uses a database file and WAL. Use the authenticated application backup
facility or SQLite's online backup mechanism; do not copy a live database file
alone and assume the WAL was included. The in-app backup/restore capability is
SQLite-only. PostgreSQL needs provider snapshots/PITR or `pg_dump`/`pg_restore`
and separate branding/configuration backup.

## Restore drill

1. Choose a backup and record its timestamp, source revision and key versions.
2. Restore into a separate instance with public ingress and outbound providers
   disabled. Keep the real application isolated while investigating.
3. Verify database integrity and migration version. Migrate using the matching
   checkout/image (`driftwatch migrate`) only after preserving the restored copy.
4. Verify users, organization boundaries, monitor selectors, previous snapshots,
   branding and decryption. Inspect queue/analysis/delivery states before resuming.
5. Run a baseline and change against an owned fixture with AI disabled. Confirm
   no paid/email/webhook provider was contacted during the drill.
6. Re-establish integrations deliberately, verify readiness JSON and Operations,
   and record the elapsed recovery time and recoverable data window.

The application SQLite restore rotates every user's session generation. Existing
sessions and old purpose tokens become invalid; users must sign in again. A raw
database/provider restore outside that application path does not perform its
revocation procedure automatically. Rotate session authentication material and
review account/provider generations before exposing a raw restored instance.

## Interrupted checks and analysis

Do not edit queue rows to claim success. A process crash leaves a lease that can
expire and be reclaimed. Check attempts remain bounded even after repeated hard
crashes. A dead check is visible to the instance operator; an audited redrive
creates new work with a reason, ticket and idempotency key while retaining the
original incident.

Analysis states distinguish `pending`, `processing`, `error`, `quota_blocked`
from `succeeded`, `disabled`, `not_requested` and `skipped_no_delivery`.
Quota exhaustion is unfinished work and remains visible for retry. Fix the
provider configuration/quota first, then retry the stored change. New analysis
appends a historical run instead of deleting earlier model/rules/verdict evidence.

History pruning retains pending/error/quota work, action-required retries and
undelivered rows, including the snapshots needed to explain them. Prolonged
outages can therefore exceed the nominal history count. Resolve incidents and
monitor disk usage rather than force-delete that evidence.

## Interrupted delivery

An explicitly selected incomplete SMTP/Brevo configuration fails closed and
remains recoverable. Log mode is a deliberate local mode and does not send mail.
Delivery leases use a current clock per recipient, bounded provider timeouts and
conditional completion. A stale owner cannot mark an expired/stolen claim sent.

Provider acceptance followed by a crash is ambiguous. Notifications are at least
once; review provider logs and message identifiers before manually resending an
exhausted message. A repeated send can reach the recipient twice.

Failure-alert suppression is measured from the last actual alert send. Suppressed
checks do not keep extending the window, and a failed alert does not become a
successful send timestamp.

## Storage exhaustion

Pause new work and preserve the failed-write logs. Expand/move storage without
deleting the only database or backup. After storage is healthy, check database
integrity and readiness, allow legitimate expired leases to recover, and rerun
the affected verification. Tests that failed with disk-write errors provide no
evidence about program correctness. Docker images, browser downloads, build
caches, backups and WAL all consume space beyond the database itself.

See [installation](INSTALL.md) and [deployment](DEPLOY.md). Measure recovery time
and the recoverable data window on your own installation before relying on backups.
