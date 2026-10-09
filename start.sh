#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/driftwatch ]; then
    printf '%s\n' 'Run sh install.sh first.' >&2
    exit 1
fi
exec .venv/bin/driftwatch
