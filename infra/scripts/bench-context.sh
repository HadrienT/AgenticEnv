#!/usr/bin/env bash
# Benchmarks a set of ctx_size values: VRAM per GPU, system RAM, prompt/gen
# tok/s, startup time. Results feed configs/models.yaml:validated_ctx_sizes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTX_SIZES=(${AGX_BENCH_CTX_SIZES:-8192 16384 32768 65536})
LLAMA_BASE_URL="${AGX_LLM_BASE_URL:-http://127.0.0.1:8000}"
OUT_FILE="${AGX_BENCH_OUT_FILE:-/opt/llm/logs/bench-context.$(date -u +%Y%m%dT%H%M%SZ).md}"
STARTUP_TIMEOUT_S="${AGX_BENCH_STARTUP_TIMEOUT_S:-120}"
PROMPT="${AGX_BENCH_PROMPT:-Write a one-sentence description of a binomial option pricing tree.}"

: "${AGX_LLAMA_ENV_FILE:=/etc/llm/llama-server.env}"
[[ -f "$AGX_LLAMA_ENV_FILE" ]] || { echo "ERROR: $AGX_LLAMA_ENV_FILE missing. Run render-llama-env.sh." >&2; exit 1; }

mkdir -p "$(dirname "$OUT_FILE")" 2>/dev/null || true
{
  echo "# Context size benchmark — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "| ctx_size | startup_s | vram_gpu0_mib | vram_gpu1_mib | ram_used_mib | prompt_tok_s | gen_tok_s |"
  echo "|---|---|---|---|---|---|---|"
} > "$OUT_FILE"

wait_ready() {
  local deadline=$((SECONDS + STARTUP_TIMEOUT_S))
  while (( SECONDS < deadline )); do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "${LLAMA_BASE_URL}/v1/models" 2>/dev/null)"
    code="${code:-000}"
    [[ "$code" == "200" ]] && return 0
    sleep 1
  done
  return 1
}

for ctx in "${CTX_SIZES[@]}"; do
  echo "=== ctx_size=$ctx ===" >&2
  export LLAMA_CTX_SIZE="$ctx"
  # Override just the ctx size in a scratch copy of the rendered env file.
  scratch_env="$(mktemp)"
  sed "s/^LLAMA_CTX_SIZE=.*/LLAMA_CTX_SIZE=${ctx}/" "$AGX_LLAMA_ENV_FILE" > "$scratch_env"

  start_ts=$SECONDS
  AGX_LLAMA_ENV_FILE="$scratch_env" "$SCRIPT_DIR/run-llama-server.sh" >/tmp/llama-bench-$ctx.log 2>&1 &
  server_pid=$!

  if wait_ready; then
    startup_s=$((SECONDS - start_ts))
    vram="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | tr '\n' ' ')"
    vram0="$(awk '{print $1}' <<< "$vram")"
    vram1="$(awk '{print $2}' <<< "$vram")"
    ram_used_mib="$(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{printf "%d", (t-a)/1024}' /proc/meminfo)"

    resp_start=$(date +%s.%N)
    resp="$(curl -s --max-time 60 "${LLAMA_BASE_URL}/completion" \
      -H 'Content-Type: application/json' \
      -d "{\"prompt\": \"${PROMPT}\", \"n_predict\": 64}" || echo '{}')"
    resp_end=$(date +%s.%N)
    elapsed="$(awk -v a="$resp_start" -v b="$resp_end" 'BEGIN{printf "%.3f", b-a}')"
    predicted_ms="$(printf '%s' "$resp" | grep -o '"predicted_ms":[0-9.]*' | cut -d: -f2 || echo "")"
    predicted_n="$(printf '%s' "$resp" | grep -o '"predicted_n":[0-9]*' | cut -d: -f2 || echo "")"
    prompt_ms="$(printf '%s' "$resp" | grep -o '"prompt_ms":[0-9.]*' | cut -d: -f2 || echo "")"
    prompt_n="$(printf '%s' "$resp" | grep -o '"prompt_n":[0-9]*' | cut -d: -f2 || echo "")"
    gen_tok_s="n/a"; prompt_tok_s="n/a"
    if [[ -n "$predicted_ms" && -n "$predicted_n" && "$predicted_ms" != "0" ]]; then
      gen_tok_s="$(awk -v n="$predicted_n" -v ms="$predicted_ms" 'BEGIN{printf "%.1f", n/(ms/1000)}')"
    fi
    if [[ -n "$prompt_ms" && -n "$prompt_n" && "$prompt_ms" != "0" ]]; then
      prompt_tok_s="$(awk -v n="$prompt_n" -v ms="$prompt_ms" 'BEGIN{printf "%.1f", n/(ms/1000)}')"
    fi

    echo "| $ctx | $startup_s | ${vram0:-n/a} | ${vram1:-n/a} | ${ram_used_mib:-n/a} | $prompt_tok_s | $gen_tok_s |" >> "$OUT_FILE"
  else
    echo "| $ctx | timeout | - | - | - | - | - |" >> "$OUT_FILE"
  fi

  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
  rm -f "$scratch_env"
done

echo "written: $OUT_FILE"
cat "$OUT_FILE"
