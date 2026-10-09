# Deployment

The tested reference is a single Linux Docker host with Compose: one
API/scheduler, one browser worker, a dedicated firewall namespace and SQLite or
PostgreSQL. The browser receives only its capture service token and capacity
settings. It does not receive the database, session, encryption, AI, mail or
bootstrap administrator credentials.

## Local reference

Follow [INSTALL](INSTALL.md) to create `.env` and start the stack. Compose starts
the firewall before the worker; API readiness probes the authenticated worker
control endpoint. A worker-side loopback health probe is disabled because it
would require weakening the browser's loopback deny rule. Inspect `/healthz`
JSON: HTTP 200 alone does not prove that capture is available.

The worker is non-root, read-only, `cap_drop: ALL`, with `no-new-privileges`,
bounded temporary/shared memory, CPU, memory, PIDs, active work and queue limits.
Only the credential-free firewall has `NET_ADMIN`. The two containers share
network namespace, not application data or process namespace.

The Docker Python targets use the pinned Wolfi/glibc runtime described in
[IMAGE_SECURITY.md](IMAGE_SECURITY.md), including two verified X.org upstream
backports. Linux x86_64 is the validated native image architecture; other
architectures require new locks and compatibility tests. The worker installs
Playwright's headless shell with Noto Latin/Polish, Arabic, CJK and emoji fonts;
the source installer retains full Chromium for the local headed picker.

## Connection-time browser boundary

The firewall sets default DROP before reporting healthy. It permits established
replies, private control requests arriving at TCP 8090, Docker's embedded DNS at
127.0.0.11, and public IPv4 TCP. It rejects new outbound connections to loopback,
private, link-local, CGNAT, documentation/benchmark, multicast and reserved
ranges. Cloud metadata is covered by the link-local deny. IPv6 is fail-closed.

This packet policy covers connections made after a fresh DNS lookup, browser
subresources, redirects and WebSockets. Application URL/DNS checks remain defense
in depth. They do not alone close the resolve-to-connect window. Do not attach
other workloads to the control network or expose port 8090 publicly.

`scripts/docker_smoke.py` creates owned HTTP fixtures at private, CGNAT,
link-local and public-class IPs on isolated Docker networks. It proves the
fixture sockets are live, then proves the worker blocks the forbidden sockets
and permits the owned public-class fixture. It drives the real authenticated
API through baseline/change with AI disabled. The synthetic public-class route
is confined to the test network; no request goes to its real Internet owner.
Run `python scripts/docker_smoke.py` before changing this topology.

## Public host

1. Complete first-owner setup before exposing the host: explicitly enable
   `DRIFTWATCH_INITIAL_ADMIN_SIGNUP_ENABLED` and register once, or use
   `python scripts/bootstrap_env.py --seed-admin`. Disable the initial-signup
   flag or remove the seed password from long-lived configuration after verifying
   the account. Keep ongoing public registration and billing disabled unless their
   intended lifecycle is configured. The initial database claim cannot be reopened
   by changing a flag or deleting users.
2. Place the API behind HTTPS, set the exact HTTPS `DRIFTWATCH_BASE_URL`, and keep
   the internal worker/database unexposed. Restrict API binding/publishing to the
   reverse proxy where appropriate. Preserve Origin checks and secure cookies.
3. Store three independent keys in a secret manager or restricted configuration.
   Back up the encryption-key rings independently. Never mount `.env` into the worker.
4. Run one API/scheduler replica. Login address/IP budgets are process-local;
   distributed deployments require shared throttling or an equivalent edge budget.
5. Give API-originated HTTP/mail/webhook/linked-document traffic an independent
   host egress policy with narrow exact database/worker exceptions. The browser
   firewall is not an API firewall. Use the application's pinned clients as well.
6. Configure a real email provider completely before relying on invitations or
   password reset. Incomplete selected SMTP/Brevo is a recoverable error; Log
   mode is deliberately local and does not deliver mail.
7. Mount durable database/branding storage and arrange off-host backup/restore
   drills. Measure free disk, WAL, queue age, dead jobs, analysis errors, quota
   blocks, delivery exhaustion and worker health through Operations.
8. Exercise an owned monitor and restart/crash recovery before enabling a real
   schedule. Preserve unresolved history and inspect at-least-once mail ambiguity.

Administrators on an exposed instance enroll TOTP. The first owner also
administers their home organization and can manage it through that membership.
Operator access to another organization's resources requires step-up and a
time-limited organization-bound support grant with an audited reason.

## PostgreSQL and hosted platforms

The Compose `postgres` profile uses a fixed local-only test password and an
internal database network. Select it explicitly using the URL documented in
[INSTALL](INSTALL.md). Production PostgreSQL requires separately managed
credentials, backups and a connection budget. Startup migrations require access
to the selected database; `driftwatch migrate` is the release-time command.

The API image target is `runtime`, the browser target is `capture-worker`, and
the policy target is `capture-firewall`. Source builders that build the last
Docker stage may use `DRIFTWATCH_IMAGE_TARGET`. The worker must never inherit
API service variables through a shared platform variable group.

Railway/Supabase configuration files are integration starting points. A platform
that cannot supply the dedicated namespace and `NET_ADMIN` firewall needs an
equivalent tested network policy/egress proxy before browser exposure. Do not
claim managed hosting is safe merely because the isolated browser image boots.
In-process capture removes the credential and network boundary and is only a
trusted local development compatibility mode.

## Release evidence

CI verifies source locks, Windows/Linux tests, Chromium, PostgreSQL migrations,
frontend, image scans/SBOMs, and the real Docker smoke. Passing repository CI does
not certify an operator's backups, public ingress, configured providers or
capacity. Record the exact source revision/image digest and deployment checks.
See [recovery](RECOVERY.md), [security](../SECURITY.md) and [FAQ](FAQ.md).
