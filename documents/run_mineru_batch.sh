#!/usr/bin/env bash
# Batch-converts a list of PDFs through MinerU (pipeline backend, forced OCR to
# avoid the ligature-drop bug seen with text-layer extraction) then through
# mineru_adapter.py into kbase's Markdown dialect.
#
# pipeline (not hybrid-engine) is deliberate: hybrid-engine's per-region VLM
# "Predict" stage exhibits a progressive slowdown within a single document
# (observed dropping from ~9 it/s to ~1 it/s over a few minutes) that on at
# least one document became an outright hang. pipeline uses dedicated
# layout/OCR/formula/table models instead of sequential VLM generation and
# converted the same 27-page reference paper in 60s vs several minutes, with
# equal or better equation/context fidelity in side-by-side comparison.
# Resumable: skips a source file if its .md already exists in $RAW_DIR.
#
# Usage: run_mineru_batch.sh <file-list.txt> <out-dir> <raw-dir> [cuda-device]
# <file-list.txt>: one absolute PDF path per line (lets the caller shard work
# across GPUs instead of a plain directory glob, which can't be split).
set -uo pipefail

FILE_LIST="$1"
OUT_DIR="$2"
RAW_DIR="$3"
CUDA_DEVICE="${4:-}"

REPO=/home/hadriensuper/AgenticEnv
MINERU="$REPO/.mineru-venv/bin/mineru"
PY="$REPO/.venv/bin/python"
ADAPTER="$REPO/documents/mineru_adapter.py"

if [ -n "$CUDA_DEVICE" ]; then
  export CUDA_VISIBLE_DEVICES="$CUDA_DEVICE"
fi

mkdir -p "$OUT_DIR" "$RAW_DIR"

while IFS= read -r pdf; do
  [ -e "$pdf" ] || continue
  id=$(basename "$pdf" .pdf)
  echo "=== $id ==="
  if [ -f "$RAW_DIR/$id.md" ]; then
    echo "skip (deja converti)"
    continue
  fi
  rm -rf "${OUT_DIR:?}/$id"
  if ! "$MINERU" -p "$pdf" -o "$OUT_DIR/$id" -b pipeline -m ocr; then
    echo "ECHEC mineru pour $id"
    continue
  fi
  json=$(find "$OUT_DIR/$id" -name "*_content_list_v2.json" | head -1)
  if [ -z "$json" ]; then
    echo "ECHEC: pas de content_list_v2.json pour $id"
    continue
  fi
  if ! "$PY" "$ADAPTER" "$json" "$RAW_DIR/$id.md"; then
    echo "ECHEC adapter pour $id"
    continue
  fi
  echo "OK -> $RAW_DIR/$id.md ($(wc -l < "$RAW_DIR/$id.md") lignes)"
done < "$FILE_LIST"

echo "=== batch termine ==="
