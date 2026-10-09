# Contributing

Use Python 3.12.15 and Node 22.12+ on the 22 release line or Node 24+. Install the
hash-locked development environment with `sh install.sh --dev` on Linux or
`.\install.ps1 -Dev` on Windows. These commands build the SPA and install Chromium.
Source setup needs the repository migrations and frontend assets; an isolated
wheel is not a complete deployment. See [INSTALL](docs/INSTALL.md).

For frontend development, run `npm run dev` in `web` with the API running. Use a
loopback base URL and add the exact development UI origin to trusted origins as
needed. Do not disable the Origin guard to resolve a proxy mismatch.

## Verification

The installers create `.venv` without activating the current shell. From the
repository root, activate it before running the checks and dependency commands.

On Windows (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
```

On Linux:

```sh
. .venv/bin/activate
```

From that activated development environment:

```sh
ruff format --check .
ruff check .
mypy src
pytest -q
pip-audit
python scripts/secret_scan.py
```

In `web`: `npm ci`, `npm audit --audit-level=high`, `npm run lint`, `npm run test`
and `npm run build`. CI additionally exercises PostgreSQL and
`python scripts/docker_smoke.py` against built images.

Run Ruff from the repository root: the whole-tree commands also cover historical
migrations and the brand asset helper. Frontend domain boundaries and the shared
settings draft are described in [Architecture](docs/ARCHITECTURE.md#frontend-boundaries).
Query implementations import shared helpers directly and keep the public
`@/lib/queries` facade free of implementation logic.

Tests use fake AI/mail/webhook providers and owned HTTP fixtures. Real Chromium
tests are included; install its binaries/system packages before the backend
suite. Never add paid-provider calls or third-party target requests to ordinary
CI. A test should expose a behavioral defect, including an appropriate negative
control for difficult reliability/security guarantees.

## Dependency changes

Install uv from the development lock and regenerate with these universal
commands. Existing pins are retained unless dependency constraints force a change;
use a deliberate `--upgrade-package NAME` for a reviewed update.

```sh
uv pip compile requirements-installer.in -o requirements-installer.lock --universal --python-version 3.12 --generate-hashes --only-binary=:all: --emit-build-options
uv pip compile requirements-tools.in -o requirements-tools.lock --universal --python-version 3.12 --generate-hashes --only-binary=:all: --emit-build-options
uv pip compile requirements-build.in -o requirements-build.lock --universal --python-version 3.12 --generate-hashes --only-binary=:all: --emit-build-options
uv pip compile pyproject.toml --universal --python-version 3.12 --generate-hashes -o requirements.lock
uv pip compile pyproject.toml --extra dev --universal --python-version 3.12 --generate-hashes -o requirements-dev.lock
```

Keep `[build-system].requires` equal to `requirements-build.in`; builds use the
locked backend without PEP 517 network isolation. Verify clean installs on both
Windows/Linux, `pip-audit`, `npm audit`, actual behavior and Docker after changes.
A successful resolver alone is insufficient. Image OS/browser advisories are a
separate release gate from application package audits.

## Changes and reviews

- Explain the concrete problem, resulting behavior and evidence in a focused PR.
- Schema changes include an Alembic migration and upgrade/concurrency coverage.
- Preserve ownership tokens, tenant filters and durable side-effect evidence.
- User-facing strings go into both English/Polish catalogs.
- Comments explain a non-obvious reason; remove obsolete code and placeholders.
- Update relevant guides and `CHANGELOG.md` when behavior changes.

Before staging, run the full secret scan. To enable the local staged gate install
`pre-commit` in your chosen developer tool environment and run `pre-commit install`.
The committed local hook calls the same checksummed scanner with `--staged`.
Never add broad allowlists to make a finding disappear. See [SECURITY](SECURITY.md).

Submit contributions only if you can license them under
[PolyForm Noncommercial 1.0.0](LICENSE). Your contribution uses the same license
as Driftwatch; it does not grant a separate right to commercial use. Preserve
[third-party notices](THIRD_PARTY_NOTICES.md) and the licenses of external code.
