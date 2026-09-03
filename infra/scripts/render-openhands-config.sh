#!/usr/bin/env bash
# Translates configs/models.yaml (active LLM) and configs/mcp/*.yaml (stdio MCP
# servers) into OpenHands CLI configuration:
#   - ~/.openhands/agent_settings.json  (llm.model/base_url/api_key)
#   - MCP server registrations via `openhands mcp add` (one per configs/mcp/*.yaml)
#
# This is the single point of change: swapping the active model in
# configs/models.yaml + re-running this script (no OpenHands JSON edited by
# hand). Idempotent — safe to re-run.
#
# Usage: infra/scripts/render-openhands-config.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MODELS_YAML="${REPO_ROOT}/configs/models.yaml"
MCP_DIR="${REPO_ROOT}/configs/mcp"
OH_DIR="${AGX_OPENHANDS_DIR:-$HOME/.openhands}"
OH_BIN="${AGX_OPENHANDS_BIN:-openhands}"

[[ -f "$MODELS_YAML" ]] || { echo "ERROR: $MODELS_YAML not found" >&2; exit 1; }
[[ -d "$MCP_DIR" ]] || { echo "ERROR: $MCP_DIR not found" >&2; exit 1; }
command -v uv >/dev/null 2>&1 || { echo "ERROR: uv not found on PATH" >&2; exit 1; }
command -v "$OH_BIN" >/dev/null 2>&1 || { echo "ERROR: $OH_BIN not found on PATH (uv tool install openhands --python 3.12)" >&2; exit 1; }

mkdir -p "$OH_DIR"

# --- 1. Render ~/.openhands/agent_settings.json from configs/models.yaml -----
uv run --project "$REPO_ROOT" python3 - "$MODELS_YAML" "$OH_DIR/agent_settings.json" <<'PY'
import json
import sys
import yaml

models_yaml, out_path = sys.argv[1], sys.argv[2]

with open(models_yaml, encoding="utf-8") as fh:
    data = yaml.safe_load(fh)

active = data["active"]
model = data["models"][active]
defaults = data.get("defaults", {})
host = defaults.get("host", "127.0.0.1")
port = defaults.get("port", 8000)
served_name = model["served_name"]

settings = {}
try:
    with open(out_path, encoding="utf-8") as fh:
        settings = json.load(fh)
except FileNotFoundError:
    pass
except json.JSONDecodeError:
    settings = {}

settings.setdefault("llm", {})
settings["llm"]["model"] = f"openai/{served_name}"
settings["llm"]["base_url"] = f"http://{host}:{port}/v1"
# llama-server does not enforce an API key; placeholder required by the
# OpenAI-compatible client.
settings["llm"]["api_key"] = "local-llm"

with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(settings, fh, indent=2)
    fh.write("\n")

print(f"wrote: {out_path} (model=openai/{served_name}, base_url=http://{host}:{port}/v1)")
PY

# --- 2. Register one stdio MCP server per configs/mcp/*.yaml -----------------
uv run --project "$REPO_ROOT" python3 - "$MCP_DIR" <<'PY' > /tmp/agx-openhands-mcp-servers.txt
import sys
import glob
import yaml

mcp_dir = sys.argv[1]
for path in sorted(glob.glob(f"{mcp_dir}/*.yaml")):
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if cfg.get("transport") != "stdio":
        continue
    print(cfg["name"])
PY

while IFS= read -r name; do
  [[ -z "$name" ]] && continue
  console_script="${name}-mcp"
  echo "registering MCP server: $name -> uv run --directory $REPO_ROOT $console_script"
  "$OH_BIN" mcp remove "$name" >/dev/null 2>&1 || true
  # --directory (not --project): corelib.config.Settings reads a `.env` file
  # relative to the process CWD, so the MCP subprocess must actually be
  # started *from* the repo root, not merely resolve its venv from there.
  "$OH_BIN" mcp add "$name" --transport stdio uv -- run --directory "$REPO_ROOT" "$console_script"
done < /tmp/agx-openhands-mcp-servers.txt
rm -f /tmp/agx-openhands-mcp-servers.txt

echo "done. Verify with: $OH_BIN mcp list"
