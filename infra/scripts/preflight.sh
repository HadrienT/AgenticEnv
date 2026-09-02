#!/usr/bin/env bash
# Read-only hardware/OS inventory for WP00. No side effects. Non-zero exit if a
# hard prerequisite (arch, OS, GPU count, compute capability) is missing.
set -euo pipefail

REQUIRED_COMPUTE_CAP="${AGX_REQUIRED_COMPUTE_CAP:-7.0}"
REQUIRED_GPU_COUNT="${AGX_REQUIRED_GPU_COUNT:-2}"
MIN_DISK_FREE_GIB="${AGX_MIN_DISK_FREE_GIB:-50}"

fail=0
note() { printf -- '- %-28s %s\n' "$1" "$2"; }
bad()  { printf -- '- %-28s %s\n' "$1" "$2"; fail=1; }

echo "=== preflight ==="

arch="$(uname -m)"
if [[ "$arch" == "x86_64" ]]; then note "architecture" "$arch"; else bad "architecture" "$arch (expected x86_64)"; fi

os_id="unknown"; version_id="unknown"
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
  os_id="${ID:-unknown}"
  version_id="${VERSION_ID:-unknown}"
fi
if [[ "$os_id" == "debian" && "$version_id" == "13" ]]; then
  note "os" "Debian $version_id"
else
  bad "os" "$os_id $version_id (expected debian 13)"
fi

gpu_lines="$(lspci 2>/dev/null | grep -i 'nvidia' | grep -iE 'v100|3d controller|vga' || true)"
gpu_count="$(printf '%s\n' "$gpu_lines" | grep -c . || true)"
if [[ "$gpu_count" -ge "$REQUIRED_GPU_COUNT" ]]; then
  note "gpu_count (lspci)" "$gpu_count"
else
  bad "gpu_count (lspci)" "$gpu_count (expected >= $REQUIRED_GPU_COUNT)"
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  caps="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null || true)"
  bad_cap=0
  while IFS= read -r cap; do
    [[ -z "$cap" ]] && continue
    [[ "$cap" != "$REQUIRED_COMPUTE_CAP" ]] && bad_cap=1
  done <<< "$caps"
  caps_joined="$(printf '%s' "$caps" | tr '\n' ',' | sed 's/,$//')"
  if [[ -n "$caps" && "$bad_cap" -eq 0 ]]; then
    note "compute_cap" "$caps_joined"
  else
    bad "compute_cap" "$caps_joined (expected all == $REQUIRED_COMPUTE_CAP)"
  fi
else
  bad "nvidia-smi" "not found"
fi

disk_free_gib="$(df --output=avail -B1G / 2>/dev/null | tail -n1 | tr -d ' ')"
if [[ -n "$disk_free_gib" && "$disk_free_gib" -ge "$MIN_DISK_FREE_GIB" ]]; then
  note "disk_free_gib (/)" "$disk_free_gib"
else
  bad "disk_free_gib (/)" "${disk_free_gib:-0} (expected >= $MIN_DISK_FREE_GIB)"
fi

mem_total_gib="$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)"
note "ram_total_gib" "$mem_total_gib"

echo "=== result ==="
if [[ "$fail" -eq 0 ]]; then
  echo "PASS: all hard prerequisites satisfied"
else
  echo "FAIL: at least one hard prerequisite is missing (see '-' lines above)"
fi
exit "$fail"
