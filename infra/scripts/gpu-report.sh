#!/usr/bin/env bash
# Dumps GPU topology and static properties for the installation report.
# Read-only w.r.t. hardware; only side effect is writing the report file.
set -euo pipefail

OUT_DIR="${AGX_LLM_DIR:-/opt/llm}"
OUT_FILE="${OUT_DIR}/gpu-topology.txt"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi not found" >&2
  exit 1
fi

if [[ ! -d "$OUT_DIR" ]]; then
  echo "ERROR: $OUT_DIR does not exist. Create it first:" >&2
  echo "  sudo mkdir -p $OUT_DIR && sudo chown \$USER:\$USER $OUT_DIR" >&2
  exit 1
fi
if [[ ! -w "$OUT_DIR" ]]; then
  echo "ERROR: $OUT_DIR is not writable by $(whoami)." >&2
  echo "  sudo chown \$USER:\$USER $OUT_DIR" >&2
  exit 1
fi

{
  echo "# GPU topology report — generated $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "## nvidia-smi topo -m"
  nvidia-smi topo -m 2>&1 || echo "(topo -m unavailable)"
  echo
  echo "## nvidia-smi --query-gpu"
  nvidia-smi --query-gpu=index,name,compute_cap,memory.total,pci.bus_id,pcie.link.gen.max,pcie.link.width.max --format=csv
  echo
  echo "## driver / cuda"
  nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n1
  command -v nvcc >/dev/null 2>&1 && nvcc --version | tail -n1 || echo "nvcc not found"
} > "$OUT_FILE"

echo "written: $OUT_FILE"
