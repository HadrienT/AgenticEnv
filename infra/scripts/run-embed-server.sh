#!/usr/bin/env bash
# Local embedding and reranking models for kbase and agentmem (WP13, WP19).
# On the V100s since WP19: each model takes ~0.8 GB beside the main llama-server and
# runs ~13x (embedding) to ~20x (reranking) faster than on the CPU. Set
# AGX_EMBED_ON_GPU=0 to go back to the CPU (e.g. to free the VRAM for a bigger main
# model); vectors stay compatible, only speed changes.
# Usage: run-embed-server.sh embed|rerank
set -euo pipefail

BIN="${AGX_LLAMA_SERVER:-/opt/llm/llama.cpp/build/bin/llama-server}"
MODELS="${AGX_PATHS_MODELS_DIR:-/opt/llm/models}"
THREADS="${AGX_EMBED_THREADS:-16}"
ON_GPU="${AGX_EMBED_ON_GPU:-1}"

device_args() {  # $1 = GPU index for this model
  if [ "$ON_GPU" = "1" ]; then
    echo "-ngl 99 -t 4 -c 8192 -b 4096 -ub 4096"
  else
    echo "-ngl 0 -t $THREADS -c 8192 -b 8192 -ub 8192"
  fi
}

gpu_env() {  # $1 = GPU index: restricts the process to it, or hides every GPU on CPU
  if [ "$ON_GPU" = "1" ]; then export CUDA_VISIBLE_DEVICES="$1"; else export CUDA_VISIBLE_DEVICES=""; fi
}

case "${1:?embed or rerank}" in
  embed)
    gpu_env "${AGX_EMBED_GPU:-1}"
    # CLS pooling: what bge-m3's dense retrieval is trained for (mean pooling, used
    # before WP19, degraded every vector). Changing it means re-embedding everything.
    # shellcheck disable=SC2046
    exec "$BIN" -m "$MODELS/bge-m3-q8_0.gguf" --embedding --pooling cls \
      --host 127.0.0.1 --port 8310 --parallel 1 $(device_args "${AGX_EMBED_GPU:-1}")
    ;;
  rerank)
    gpu_env "${AGX_RERANK_GPU:-0}"
    # Q8_0 rather than Q4_K_M: a cross-encoder's output is a ranking, and 4-bit
    # quantization blurs exactly the small score gaps it has to resolve.
    # shellcheck disable=SC2046
    exec "$BIN" -m "$MODELS/bge-reranker-v2-m3-Q8_0.gguf" --reranking \
      --host 127.0.0.1 --port 8311 --parallel 1 $(device_args "${AGX_RERANK_GPU:-0}")
    ;;
esac
