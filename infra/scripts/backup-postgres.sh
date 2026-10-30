#!/usr/bin/env bash
# Daily dump of the real database (WP16 §3). Custom format, so one table can be
# restored alone. Outside the Docker volume on purpose: losing the volume must
# not lose the backups. Restore procedure: docs/runbook.md.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
set -a; . ./.env; set +a

DIR="${AGX_BACKUP_DIR:-$HOME/backups/agenticenv}"
KEEP_DAYS="${AGX_BACKUP_KEEP_DAYS:-14}"
target="$DIR/${AGX_DB_NAME}-$(date +%Y%m%dT%H%M%S).dump"

mkdir -p "$DIR"
chmod 700 "$DIR"
docker exec -e PGPASSWORD="$AGX_DB_ADMIN_PASSWORD" agenticenv-postgres \
  pg_dump -U "$AGX_DB_ADMIN_USER" -d "$AGX_DB_NAME" -Fc > "$target.partial"
mv "$target.partial" "$target"
chmod 600 "$target"
find "$DIR" -name '*.dump' -mtime +"$KEEP_DAYS" -delete
echo "$target ($(du -h "$target" | cut -f1))"
