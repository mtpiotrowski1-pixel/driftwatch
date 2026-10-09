# Installation and updates

## Reference Docker deployment

Use Linux containers, Docker Engine/Desktop with Compose v2, and Python 3.12+
for the standard-library configuration helper. The native image is validated on
Linux x86_64. Keep at least 10 GB free for images, Chromium and build cache before
building. The initial native build can take several minutes. From the repository root:

```sh
python scripts/bootstrap_env.py
docker compose up --build -d
docker compose ps
```

The helper creates `.env` exclusively: an existing file is never replaced. The
session signing key, encryption key and capture service token are independent
random values. It enables one-time first-account setup; ongoing public signup
and billing remain disabled. No administrator password is stored in the default
generated configuration. Keep `.env` private; on Windows restrict its ACL to the
service operator. On POSIX it is created 0600.

Open http://localhost:8000 and register the first account. It becomes both the
instance operator and administrator of the default organization. Sign in,
enroll TOTP when prompted and store the recovery codes offline. Open
**Organizations → Manage** to enter your workspace and add a monitor; managing
your own organization does not require a support grant. To invite another user,
configure a real mail channel first. See the
[administrator guide](ADMIN_GUIDE.en.md).

The reference stack publishes port 8000 on `127.0.0.1` only. The API, isolated
browser and firewall must all be running. `/healthz` can return
HTTP 200 with `status=degraded` while capture is unavailable: inspect the JSON,
not just the HTTP code. Do not publish this HTTP development endpoint externally.

If `.env` already exists, review all three independent keys and the initial
signup setting described below. The helper will not overwrite your configuration.

Stop without deleting data: `docker compose down`. Start again with
`docker compose up -d`. Do not use `down --volumes` on a database you want to keep.

## Source installation on Windows

Install a bootstrap Python **3.12+** (with the `py` launcher), Git, and Node **22.12+ on the 22
release line, or 24+**. In PowerShell at the repository root:

```powershell
.\install.ps1 -Dev
.\start.ps1
```

The installer uses the checked-in hash locks and an isolated `.venv-bootstrap`
to install pinned uv. uv downloads managed **Python 3.12.15**, including Windows
security builds from [Astral's Python distributions](https://docs.astral.sh/uv/concepts/python-versions/).
The PSF's current 3.12 security releases are source-only. It creates `.venv` only
when absent, refuses an older patch or different minor version, installs Chromium, runs `npm ci` and
builds the SPA. It preserves `.env` and runtime data. An older environment can be
kept under a different name; the installer will not replace it for you.

Both source installers require the checkout's own `.venv`; a system interpreter,
shared environment, symlink or junction is rejected before dependency updates.
When upgrading a supported existing environment, they remove only the obsolete
`lxml` package after installing the current dependency lock, then verify that its
metadata and import are absent. Other manually installed packages are retained;
`pip check` must pass after the application update.

## Source installation on Linux

Install a bootstrap Python 3.12+ with venv support, Git, and the same Node versions.
The installer selects the same managed Python 3.12.15 runtime:

```sh
sh install.sh --dev
sh start.sh
```

Playwright's `--with-deps` installs system browser packages and may ask for sudo.
For machines where that is unsuitable, use the Docker deployment instead.
Local in-process capture is intended for a trusted development machine. It does
not provide the container credential boundary or packet firewall.

Source installs require the checkout: migrations, `alembic.ini` and built
`web/dist` are repository resources, not all part of the Python wheel. A wheel
by itself is not a complete deployment. Docker assembles these resources.

Open http://localhost:8000 after starting. In a fresh local source installation,
use the registration screen to create the first account; it becomes the instance
operator and administrator of the default organization. Automatic local setup
requires loopback values for both `DRIFTWATCH_BASE_URL` and `DRIFTWATCH_HOST`.
For a non-loopback runtime, explicitly configure initial signup or seed an
administrator before exposure; follow [deployment configuration](DEPLOY.md).

If you reuse `.env` from the Docker configuration helper, review its capture
settings first. For local in-process capture remove `DRIFTWATCH_CAPTURE_WORKER_TOKEN`
and leave `DRIFTWATCH_CAPTURE_WORKER_URL` unset. To use the isolated worker, set
both to the token and an HTTPS worker URL reachable from the source application.
Plain HTTP requires `DRIFTWATCH_CAPTURE_WORKER_ALLOW_INSECURE_HTTP=true` and is
intended only for a verified private network on one host.
The application refuses a token without a URL (or a URL without a token).

## First account and registration

Each new installation uses its own database. The first **successful**
registration on a fresh database claims the administrator/operator role in a
single transaction. Concurrent attempts cannot create two initial operators.
The claim is durable: restarting, changing signup flags or deleting accounts
does not reopen first-owner setup. Upgrading an existing database neither
promotes its users nor replaces their passwords.

Local loopback source installations allow first-account setup automatically.
For a non-loopback runtime, including the API inside Compose, set
`DRIFTWATCH_INITIAL_ADMIN_SIGNUP_ENABLED=true` explicitly. The configuration
helper enables it for the reference Compose stack, whose published port stays
on loopback. This flag opens **initial setup only**, not registration after
the owner exists. Finish that setup before exposing the instance publicly,
then remove or disable the flag in long-lived configuration.

Alternatively, run `python scripts/bootstrap_env.py --seed-admin` before the
first start. It asks for an initial email and password and writes
`DRIFTWATCH_INITIAL_ADMIN_EMAIL` / `DRIFTWATCH_INITIAL_ADMIN_PASSWORD` together
with the generated keys. This is an explicit alternative to UI setup. Remove
the bootstrap password from long-lived configuration after verifying the
account; it does not change an existing user's password.

Further accounts normally use administrator invitations. Ongoing registration
is a separate opt-in setting, `DRIFTWATCH_PUBLIC_REGISTRATION_ENABLED`, and does
not award the instance operator role. For an existing installation with no
working operator, use a reviewed recovery procedure rather than trying to
reopen initial signup or removing its marker.

## PostgreSQL

The optional profile starts a database; it does not automatically select it.
For a disposable local parity environment, set this in your private `.env`:

```dotenv
DRIFTWATCH_DATABASE_URL=postgresql+asyncpg://driftwatch:driftwatch@postgres:5432/driftwatch
```

Then run `docker compose --profile postgres up --build -d`. The fixed profile
password is for a private local database only. Use separately managed credentials
and backups for a public deployment. Changing the URL does not migrate existing
SQLite data. Startup applies Alembic migrations to the selected database.

## Updating

1. Back up the database, branding data and encryption-key rings; verify a restore
   in a separate instance before a material upgrade.
2. Stop capture/check scheduling, preserve pending work and record the source revision.
3. Update source and rebuild: `docker compose up --build -d`. For source installs,
   run the corresponding installer to consume the new locks and SPA.
4. Check readiness JSON and Operations. Confirm a baseline and a real change on
   an owned test page, then resume normal scheduling.

Database downgrades are not an automatic rollback plan. Restore a compatible
backup with the matching old revision and key rings if a migration cannot be
reversed safely. See [recovery](RECOVERY.md) and [deployment](DEPLOY.md).

## Common problems

- `email_not_configured`: an explicitly selected SMTP/Brevo channel is incomplete.
  Configure that provider fully or deliberately select Log for local debugging.
- Container healthy but capture unavailable: inspect `/healthz` dependencies and
  Operations; verify the worker token, firewall health and worker process.
- Disk full / `Input/output error`: stop new checks, free or expand storage, then
  rerun affected tests and recover leases. Failed writes do not establish correctness.
- Selector missing, HTTP error or anti-bot block: retain the old baseline, repair
  the selector/access policy, and run an owned check. Do not reset to the error page.
- Browser cannot reach IPv6-only pages: the reference firewall currently permits
  IPv4 public TCP only. Supply and verify an equivalent IPv6 policy before enabling it.

More answers: [FAQ](FAQ.md).
