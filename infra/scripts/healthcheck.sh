#!/usr/bin/env bash
# Aggregated system health check (07-ERRORS-AND-LOGGING.md §6). Emits JSON on
# stdout, exit 0 if no CRITICAL check failed, 1 otherwise.
set -uo pipefail

LLAMA_BASE_URL="${AGX_LLM_BASE_URL:-http://127.0.0.1:8000}"
PG_HOST="${AGX_DB_HOST:-127.0.0.1}"
PG_PORT="${AGX_DB_PORT:-5432}"
MIN_DISK_FREE_GIB="${AGX_MIN_DISK_FREE_GIB:-50}"
MIN_RAM_FREE_GIB="${AGX_MIN_RAM_FREE_GIB:-4}"
REQUIRED_COMPUTE_CAP="${AGX_REQUIRED_COMPUTE_CAP:-7.0}"
REQUIRED_GPU_COUNT="${AGX_REQUIRED_GPU_COUNT:-2}"

# name|status(ok|warning|error|critical)|detail
checks=()
add_check() { checks+=("$1|$2|$3"); }

# --- GPU ---
if command -v nvidia-smi >/dev/null 2>&1; then
  caps="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null)"
  count="$(printf '%s\n' "$caps" | grep -c . || true)"
  bad_cap=0
  while IFS= read -r cap; do
    [[ -z "$cap" ]] && continue
    [[ "$cap" != "$REQUIRED_COMPUTE_CAP" ]] && bad_cap=1
  done <<< "$caps"
  if [[ "$count" -ge "$REQUIRED_GPU_COUNT" && "$bad_cap" -eq 0 ]]; then
    add_check "gpu_count" "ok" "$count x GPU, compute cap $REQUIRED_COMPUTE_CAP"
  else
    add_check "gpu_count" "critical" "found $count GPU(s), expected >= $REQUIRED_GPU_COUNT at cap $REQUIRED_COMPUTE_CAP"
  fi
else
  add_check "gpu_count" "critical" "nvidia-smi not found"
fi

# --- llama-server ---
llama_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "${LLAMA_BASE_URL}/v1/models" 2>/dev/null)"
llama_code="${llama_code:-000}"
if [[ "$llama_code" == "200" ]]; then
  add_check "llama_server" "ok" "GET /v1/models 200"
else
  add_check "llama_server" "critical" "GET /v1/models -> $llama_code"
fi

# --- VRAM / no CPU offload (heuristic: llama-server must show a compute process on every GPU) ---
if [[ "$llama_code" == "200" ]] && command -v nvidia-smi >/dev/null 2>&1; then
  procs="$(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader 2>/dev/null | grep -c . || true)"
  if [[ "$procs" -ge 1 ]]; then
    add_check "no_cpu_offload" "ok" "$procs GPU compute process(es) detected"
  else
    add_check "no_cpu_offload" "critical" "llama-server is up but no GPU compute process found"
  fi
else
  add_check "no_cpu_offload" "critical" "cannot verify: llama-server not reachable"
fi

# --- PostgreSQL ---
if (exec 3<>"/dev/tcp/${PG_HOST}/${PG_PORT}") 2>/dev/null; then
  exec 3>&- 3<&-
  add_check "postgres" "ok" "TCP ${PG_HOST}:${PG_PORT} open"
else
  add_check "postgres" "critical" "cannot connect to ${PG_HOST}:${PG_PORT}"
fi

# --- migrations (delegated to corelib once it exists) ---
add_check "migrations" "critical" "not verifiable yet: corelib.db not installed (WP01)"

# --- embeddings dimension (delegated to kbase once it exists) ---
add_check "embeddings_dimension" "critical" "not verifiable yet: kbase not installed (WP04/WP05)"

# --- MCP servers (substitution table: quantlab -> cppdev/codeintel/qmharness) ---
check_mcp() {
  local name="$1" port="$2"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:${port}/health" 2>/dev/null)"
  code="${code:-000}"
  if [[ "$code" == "200" ]]; then
    add_check "$name" "ok" "GET /health 200 on :${port}"
  else
    add_check "$name" "error" "GET /health -> $code on :${port}"
  fi
}
check_mcp "mcp_cppdev"   "${AGX_MCP_CPPDEV_PORT:-8201}"
check_mcp "mcp_kbase"    "${AGX_MCP_KBASE_PORT:-8202}"
check_mcp "mcp_agentmem" "${AGX_MCP_AGENTMEM_PORT:-8203}"
check_mcp "mcp_codeintel" "${AGX_MCP_CODEINTEL_PORT:-8204}"
check_mcp "mcp_qmharness" "${AGX_MCP_QMHARNESS_PORT:-8205}"

# --- Docker + GPU runtime ---
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -qi nvidia; then
      add_check "docker_gpus" "ok" "docker daemon up, nvidia runtime registered"
    else
      add_check "docker_gpus" "error" "docker daemon up, nvidia runtime not registered"
    fi
  else
    add_check "docker_gpus" "error" "docker daemon not reachable"
  fi
else
  add_check "docker_gpus" "error" "docker not installed"
fi

# --- Disk / RAM ---
disk_free_gib="$(df --output=avail -B1G / 2>/dev/null | tail -n1 | tr -d ' ')"
if [[ -n "$disk_free_gib" && "$disk_free_gib" -ge "$MIN_DISK_FREE_GIB" ]]; then
  add_check "disk_free" "ok" "${disk_free_gib} GiB free"
else
  add_check "disk_free" "warning" "${disk_free_gib:-0} GiB free (< ${MIN_DISK_FREE_GIB})"
fi

ram_free_gib="$(awk '/MemAvailable/ {printf "%d", $2/1024/1024}' /proc/meminfo)"
if [[ -n "$ram_free_gib" && "$ram_free_gib" -ge "$MIN_RAM_FREE_GIB" ]]; then
  add_check "ram_free" "ok" "${ram_free_gib} GiB available"
else
  add_check "ram_free" "warning" "${ram_free_gib:-0} GiB available (< ${MIN_RAM_FREE_GIB})"
fi

# --- render JSON ---
overall_ok=true
for c in "${checks[@]}"; do
  IFS='|' read -r _ status _ <<< "$c"
  [[ "$status" == "critical" ]] && overall_ok=false
done

json="{\n  \"ok\": ${overall_ok},\n  \"checks\": [\n"
n="${#checks[@]}"
for i in "${!checks[@]}"; do
  IFS='|' read -r name status detail <<< "${checks[$i]}"
  detail_escaped="${detail//\"/\\\"}"
  comma=","
  [[ "$i" -eq $((n-1)) ]] && comma=""
  json+="    {\"name\": \"${name}\", \"status\": \"${status}\", \"detail\": \"${detail_escaped}\"}${comma}\n"
done
json+="  ]\n}"

printf '%b\n' "$json"

if [[ "$overall_ok" == "true" ]]; then exit 0; else exit 1; fi
