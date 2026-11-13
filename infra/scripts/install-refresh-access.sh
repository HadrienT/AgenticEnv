#!/usr/bin/env bash
# Lets Airflow (~/data-ingest, DAG `kbase_regulation_refresh`) start the monthly
# regulation refresh on this host, and nothing else (WP21 §8.1).
#
# 1. A new ed25519 key, made for this purpose only.
# 2. Its public half in ~/.ssh/authorized_keys with `restrict` (no shell, no tty, no
#    forwarding), `from=` the Docker networks only, and a forced command: whatever the
#    client sends, the key runs kbase-regulation-refresh.sh. Same pattern as the Atlas
#    probes key.
# 3. The Airflow connection `kbase_refresh_ssh` (private key + this host's key) in the
#    data-ingest scheduler; the local copy of the private key is then deleted.
#
# Re-running replaces the key (the old authorized_keys line is removed first).
#
#   bash infra/scripts/install-refresh-access.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST_IP="${AGX_REFRESH_HOST_IP:-172.17.0.1}"          # the host as containers reach it
FROM_NETS="${AGX_REFRESH_FROM:-172.16.0.0/12}"        # Docker's default address pools
SCHEDULER="${AGX_AIRFLOW_SCHEDULER:-data-ingest-airflow-scheduler-1}"
CONN_ID="kbase_refresh_ssh"
TAG="kbase-regulation-refresh"
KEYS="$HOME/.ssh/authorized_keys"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

ssh-keygen -q -t ed25519 -N "" -C "$TAG" -f "$work/key"

mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
touch "$KEYS" && chmod 600 "$KEYS"
grep -v " $TAG\$" "$KEYS" > "$work/keys" || true
command="/bin/bash $REPO/infra/scripts/kbase-regulation-refresh.sh"
echo "restrict,from=\"$FROM_NETS\",command=\"$command\" $(cat "$work/key.pub")" >> "$work/keys"
cat "$work/keys" > "$KEYS"
echo "==> authorized_keys: forced command for $TAG"

host_key="$(cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub)"
extra="$(python3 -c 'import json,sys; print(json.dumps({"private_key": open(sys.argv[1]).read(), "known_hosts": sys.argv[2]}))' \
  "$work/key" "$HOST_IP $host_key")"
docker exec "$SCHEDULER" airflow connections delete "$CONN_ID" >/dev/null 2>&1 || true
docker exec "$SCHEDULER" airflow connections add "$CONN_ID" \
  --conn-type ssh --conn-host "$HOST_IP" --conn-login "$USER" \
  --conn-description "Starts the kbase regulation refresh on the host (forced command)" \
  --conn-extra "$extra" >/dev/null
echo "==> Airflow connection $CONN_ID registered in $SCHEDULER"
echo "    Unpause the DAG kbase_regulation_refresh in the Airflow UI to schedule it."
