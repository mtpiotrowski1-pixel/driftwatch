#!/bin/sh
set -eu
cd "$(dirname "$0")"
for environment in .venv .venv-bootstrap; do
    if [ -L "$environment" ] || { [ -e "$environment" ] && [ ! -d "$environment" ]; }; then
        printf '%s\n' "Refusing linked or invalid $environment; existing files preserved" >&2
        exit 1
    fi
done
if [ ! -x .venv/bin/python ]; then
    if [ ! -x .venv-bootstrap/bin/python ]; then python3 -m venv .venv-bootstrap; fi
    .venv-bootstrap/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements-installer.lock
    .venv-bootstrap/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements-tools.lock
    .venv-bootstrap/bin/python -m uv venv --managed-python --python 3.12.15 .venv
    .venv-bootstrap/bin/python -m uv pip install --python .venv/bin/python --require-hashes --only-binary=:all: -r requirements-installer.lock
fi
.venv/bin/python scripts/prepare_project_environment.py --check-only
.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements-installer.lock
lock=requirements.lock
if [ "${1:-}" = "--dev" ]; then lock=requirements-dev.lock; fi
.venv/bin/python -m pip install --require-hashes -r "$lock"
.venv/bin/python scripts/prepare_project_environment.py
.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements-build.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m pip check
.venv/bin/python -m playwright install --with-deps chromium
(cd web && npm ci && npm run build)
printf '%s\n' 'Installed. Run sh start.sh. Docker Compose provides the isolated worker and socket firewall.'
