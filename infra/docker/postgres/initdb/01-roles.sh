#!/bin/bash
# Bootstraps the app_rw login role (04-DATA-MODEL.md §9). Runs once, at first
# container init, as the POSTGRES_USER superuser; AGX_DB_USER/PASSWORD come
# from the postgres service environment (infra/docker/compose.yaml).
set -euo pipefail

: "${AGX_DB_USER:?AGX_DB_USER must be set}"
: "${AGX_DB_PASSWORD:?AGX_DB_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${AGX_DB_USER}') THEN
        CREATE ROLE "${AGX_DB_USER}" LOGIN PASSWORD '${AGX_DB_PASSWORD}';
    END IF;
END
\$\$;

GRANT ALL PRIVILEGES ON DATABASE "${POSTGRES_DB}" TO "${AGX_DB_USER}";
GRANT CREATE ON SCHEMA public TO "${AGX_DB_USER}";
EOSQL
