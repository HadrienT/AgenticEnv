#!/usr/bin/env bash
# Switch / inspect the served LLM profile (issue #16). Unprivileged wrapper
# around /usr/local/sbin/agx-llm-use (run via sudo, NOPASSWD once
# `just install-stack` has installed the rule).
#
# Usage: llm-profile.sh use <profile>   switch, then wait for /v1/models to
#                                       report the profile's served_name
#        llm-profile.sh status          current profile + what /v1/models says
set -euo pipefail

PROFILES_DIR="${AGX_LLAMA_PROFILES_DIR:-/etc/llm/profiles}"
ENV_LINK="${AGX_LLAMA_ENV_FILE:-/etc/llm/llama-server.env}"
LLAMA_BASE_URL="${AGX_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
WAIT_S="${AGX_LLM_SWITCH_TIMEOUT_S:-180}"

served_models() {
  curl -fsS --max-time 3 "${LLAMA_BASE_URL%/}/models" 2>/dev/null \
    | python3 -c 'import json,sys; print(" ".join(m["id"] for m in json.load(sys.stdin)["data"]))' \
    2>/dev/null || true
}

profile_var() {  # profile_var <env file> <VAR>
  sed -n "s/^$2=//p" "$1" | tail -n1
}

cmd="${1:-status}"
case "$cmd" in
  status)
    if [[ -f "$ENV_LINK" ]]; then
      echo "profile:  $(profile_var "$ENV_LINK" LLAMA_PROFILE || true) ($(readlink -f "$ENV_LINK"))"
    else
      echo "profile:  none ($ENV_LINK missing)"
    fi
    served="$(served_models)"
    echo "serving:  ${served:-<llama-server not answering>}"
    ;;
  use)
    profile="${2:?usage: llm-profile.sh use <profile>}"
    file="$PROFILES_DIR/$profile.env"
    [[ -f "$file" ]] || {
      echo "ERROR: $file not found. Known: $(cd "$PROFILES_DIR" 2>/dev/null && ls -- *.env 2>/dev/null | sed 's/\.env$//' | tr '\n' ' ')" >&2
      echo "Render it with: infra/scripts/render-llama-env.sh $profile" >&2
      exit 1
    }
    expected="$(profile_var "$file" LLAMA_SERVED_NAME)"
    sudo /usr/local/sbin/agx-llm-use "$profile"
    echo "waiting for /v1/models to serve '$expected' (up to ${WAIT_S}s) ..."
    for ((i = 0; i < WAIT_S; i += 2)); do
      if [[ " $(served_models) " == *" $expected "* ]]; then
        echo "ok: profile '$profile' serving '$expected'"
        exit 0
      fi
      sleep 2
    done
    echo "ERROR: llama-server did not come back on '$expected' within ${WAIT_S}s." >&2
    echo "Check: systemctl status llama-server; journalctl -u llama-server -n 50" >&2
    exit 1
    ;;
  *)
    echo "usage: llm-profile.sh use <profile> | status" >&2
    exit 2
    ;;
esac
