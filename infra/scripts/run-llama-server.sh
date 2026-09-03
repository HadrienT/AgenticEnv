#!/usr/bin/env bash
# Builds and execs the llama-server command line from /etc/llm/llama-server.env.
# This is the single point of change for context size / model (via the env file).
# No argument is ever hardcoded in the systemd unit.
set -euo pipefail

ENV_FILE="${AGX_LLAMA_ENV_FILE:-/etc/llm/llama-server.env}"
[[ -f "$ENV_FILE" ]] || { echo "ERROR: $ENV_FILE not found. Run render-llama-env.sh first." >&2; exit 1; }

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

: "${LLAMA_BIN:?LLAMA_BIN not set}"
: "${LLAMA_MODEL_PATH:?LLAMA_MODEL_PATH not set}"
: "${LLAMA_HOST:?LLAMA_HOST not set}"
: "${LLAMA_PORT:?LLAMA_PORT not set}"
: "${LLAMA_CTX_SIZE:?LLAMA_CTX_SIZE not set}"

[[ -x "$LLAMA_BIN" ]] || { echo "ERROR: $LLAMA_BIN not found or not executable." >&2; exit 1; }
[[ -f "$LLAMA_MODEL_PATH" ]] || { echo "ERROR: $LLAMA_MODEL_PATH not found." >&2; exit 1; }

args=(
  --host "$LLAMA_HOST"
  --port "$LLAMA_PORT"
  --model "$LLAMA_MODEL_PATH"
  --ctx-size "$LLAMA_CTX_SIZE"
  --n-gpu-layers "${LLAMA_N_GPU_LAYERS:-all}"
  --split-mode "${LLAMA_SPLIT_MODE:-layer}"
)

# Served model name exposed via /v1/models — WP08 needs this stable across GGUF
# swaps (OpenHands' LLM config references it, never the raw file path).
[[ -n "${LLAMA_SERVED_NAME:-}" ]] && args+=(--alias "$LLAMA_SERVED_NAME")

[[ "${LLAMA_FLASH_ATTN:-on}" == "on" ]] && args+=(--flash-attn on)
[[ "${LLAMA_CONT_BATCHING:-on}" == "on" ]] && args+=(--cont-batching)
[[ -n "${LLAMA_CHAT_TEMPLATE:-}" ]] && args+=(--chat-template "$LLAMA_CHAT_TEMPLATE")

if [[ -n "${LLAMA_EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  extra=(${LLAMA_EXTRA_ARGS})
  args+=("${extra[@]}")
fi

echo "exec: $LLAMA_BIN ${args[*]}" >&2
exec "$LLAMA_BIN" "${args[@]}"
