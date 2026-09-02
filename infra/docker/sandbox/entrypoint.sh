#!/usr/bin/env bash
# Sandbox entrypoint: refuses to run as root, always lands in /workspace.
set -euo pipefail

if [[ "$(id -u)" -eq 0 ]]; then
  echo "ERROR: sandbox must not run as root" >&2
  exit 1
fi

cd /workspace
exec "$@"
