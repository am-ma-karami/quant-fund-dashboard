#!/bin/sh
# Boot order: schema migrations run before the service starts, so a fresh
# database volume is always ready (see scripts/run_migrations.py).
# On failure the container exits non-zero and the restart policy retries.
set -e

python scripts/run_migrations.py

exec "$@"
