#!/usr/bin/env sh
set -eu

mkdir -p "${REPORTS_DIR:-/app/reports}" /data

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
fi

exec "$@"

