#!/usr/bin/env bash
# One-off (WP16 §1, issue #43): removes what the test suite left in the real
# database before it got its own. Dry run by default; `--apply` deletes.
# Take a backup first: `just backup`.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
set -a; . ./.env; set +a
DB="${AGX_DB_NAME:?}"

run() {
  docker exec -i -e PGPASSWORD="$AGX_DB_ADMIN_PASSWORD" agenticenv-postgres \
    psql -v ON_ERROR_STOP=1 -U "$AGX_DB_ADMIN_USER" -d "$DB" -At "$@"
}

echo "== what would go, in $DB =="
run <<'SQL'
SELECT 'documents', string_agg(doc_key, ', ') FROM kb.documents WHERE doc_key IN ('sample-notes', 'sample-paper');
SELECT 'qm_runs', count(*) FROM eval.qm_runs WHERE run_id LIKE 'run-store-%';
SELECT 'tool_invocations', count(*) FROM obs.tool_invocations WHERE server = 's' AND tool = 't';
SQL

if [[ "${1:-}" != "--apply" ]]; then
  echo "dry run: nothing deleted. Re-run with --apply."
  exit 0
fi

run <<'SQL'
BEGIN;
DELETE FROM kb.documents WHERE doc_key IN ('sample-notes', 'sample-paper');
DELETE FROM eval.qm_runs WHERE run_id LIKE 'run-store-%';
DELETE FROM obs.tool_invocations WHERE server = 's' AND tool = 't';
COMMIT;
SQL
echo "done."
