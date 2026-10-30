#!/usr/bin/env bash
# Local embedding and reranking models for kbase and agentmem (WP13). On CPU on
# purpose: the V100s belong to the main llama-server.
# Usage: run-embed-server.sh embed|rerank
set -euo pipefail

BIN="${AGX_LLAMA_SERVER:-/opt/llm/llama.cpp/build/bin/llama-server}"
MODELS="${AGX_PATHS_MODELS_DIR:-/opt/llm/models}"
THREADS="${AGX_EMBED_THREADS:-16}"

case "${1:?embed or rerank}" in
  embed)
    exec "$BIN" -m "$MODELS/bge-m3-q8_0.gguf" --embedding --pooling mean \
      --host 127.0.0.1 --port 8310 -ngl 0 -t "$THREADS" -c 8192 -b 8192 -ub 8192 --parallel 1
    ;;
  rerank)
    exec "$BIN" -m "$MODELS/bge-reranker-v2-m3-q4_k_m.gguf" --reranking \
      --host 127.0.0.1 --port 8311 -ngl 0 -t "$THREADS" -c 8192 -b 8192 -ub 8192 --parallel 1
    ;;
esac
