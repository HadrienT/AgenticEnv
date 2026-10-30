#!/usr/bin/env bash
# Retention of the append-only journals (WP16 §3): they only serve debugging, and
# `AGX_LOG_KEEP_DAYS` is what keeps them from growing forever.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
set -a; . ./.env; set +a
DAYS="${AGX_LOG_KEEP_DAYS:-90}"

docker exec -i -e PGPASSWORD="$AGX_DB_ADMIN_PASSWORD" agenticenv-postgres \
  psql -v ON_ERROR_STOP=1 -U "$AGX_DB_ADMIN_USER" -d "$AGX_DB_NAME" -At <<SQL
DELETE FROM obs.tool_invocations WHERE ts < now() - interval '$DAYS days';
DELETE FROM kb.retrieval_logs WHERE ts < now() - interval '$DAYS days';
SQL
