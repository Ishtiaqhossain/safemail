#!/bin/sh
# Container entrypoint. Optionally applies DB migrations, then execs the given
# command. Migrations are gated by RUN_MIGRATIONS so only one service (the API)
# runs `alembic upgrade head` — the worker/beat containers skip it and avoid a
# concurrent-migration race. Works on any container runtime; no host-specific
# release/pre-deploy hook required.
set -e

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "[entrypoint] applying database migrations..."
    alembic upgrade head
fi

exec "$@"
