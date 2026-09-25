#!/usr/bin/env bash
# Renders infra/systemd/llama-bridge.{socket,service} from the .j2 templates in
# configs/, so a Docker sandbox can reach llama-server (127.0.0.1:8000 only)
# without llama-server itself ever being exposed beyond loopback. See
# blueprint/wp/WP08b-openhands-sandbox.md §"Réseau".
#
# Read-only w.r.t. the running system: this script NEVER calls sudo and never
# installs/enables the units itself. It writes the rendered units under
# ${AGX_LLAMA_BRIDGE_OUT_DIR:-/tmp} and prints the exact commands to install
# and enable them. Idempotent — safe to re-run.
#
# Usage: infra/scripts/render-llama-bridge.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SOCKET_TEMPLATE="${REPO_ROOT}/configs/llama-bridge.socket.j2"
SERVICE_TEMPLATE="${REPO_ROOT}/configs/llama-bridge.service.j2"
SYSTEMD_DIR="/etc/systemd/system"
OUT_DIR="${AGX_LLAMA_BRIDGE_OUT_DIR:-/tmp}"

[[ -f "$SOCKET_TEMPLATE" ]] || { echo "ERROR: $SOCKET_TEMPLATE not found" >&2; exit 1; }
[[ -f "$SERVICE_TEMPLATE" ]] || { echo "ERROR: $SERVICE_TEMPLATE not found" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker not found on PATH" >&2; exit 1; }

BRIDGE_HOST="${AGX_LLAMA_BRIDGE_HOST:-$(docker network inspect bridge -f '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null || true)}"
if [[ -z "$BRIDGE_HOST" ]]; then
  echo "ERROR: could not detect the Docker default-bridge gateway (docker network inspect bridge)." >&2
  echo "Is Docker running? Set AGX_LLAMA_BRIDGE_HOST explicitly to override detection." >&2
  exit 1
fi
BRIDGE_PORT="${AGX_LLAMA_BRIDGE_PORT:-8001}"
LLAMA_PORT="${AGX_LLM_PORT:-8000}"

echo "detected Docker bridge gateway: $BRIDGE_HOST (llama-bridge will bind ${BRIDGE_HOST}:${BRIDGE_PORT})" >&2

rendered_socket="$(sed \
  -e "s/{{ BRIDGE_HOST }}/${BRIDGE_HOST}/" \
  -e "s/{{ BRIDGE_PORT }}/${BRIDGE_PORT}/" \
  "$SOCKET_TEMPLATE")"

rendered_service="$(sed \
  -e "s/{{ LLAMA_PORT }}/${LLAMA_PORT}/" \
  "$SERVICE_TEMPLATE")"

mkdir -p "$OUT_DIR"
socket_out="${OUT_DIR}/llama-bridge.socket"
service_out="${OUT_DIR}/llama-bridge.service"
printf '%s\n' "$rendered_socket" > "$socket_out"
printf '%s\n' "$rendered_service" > "$service_out"

echo "written: $socket_out"
echo "written: $service_out"
echo
echo "Nothing was installed. Review the two files above, then, ONLY when ready:" >&2
echo "  sudo install -m 0644 $socket_out $SYSTEMD_DIR/llama-bridge.socket" >&2
echo "  sudo install -m 0644 $service_out $SYSTEMD_DIR/llama-bridge.service" >&2
echo "  sudo systemctl daemon-reload" >&2
echo "  sudo systemctl enable --now llama-bridge.socket" >&2
echo "Verify with: systemctl status llama-bridge.socket" >&2
