#!/usr/bin/env bash
# WP20 step 5 batch: Basel formulas (MinerU on the chapter PDFs), then ingestion of the
# regulation manifests, a consistency check and the evaluation gates. Heavy on the GPU
# (MinerU) and the embedding server: meant to run at night, from the deployed checkout.
#
#   systemd-run --user --on-calendar='YYYY-MM-DD 01:00' --unit=kbase-regulation-ingest \
#     /bin/bash ~/AgenticEnv/infra/scripts/kbase-regulation-ingest.sh
#
# Pages and PDFs are fetched beforehand (`kbase harvest-basel`, `kbase basel-formulas
# --fetch-only`): this script makes no request to bis.org. Log and eval reports go to
# $AGX_PATHS_DOCUMENTS_DIR/logs, never into the checkout.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
set -a; . ./.env; set +a
export AGX_KBASE_CONFIG="${AGX_KBASE_CONFIG:-kbase-v2.yaml}"
export CUDA_VISIBLE_DEVICES="${KBASE_MINERU_GPU:-1}"   # MinerU only; kbase itself uses no GPU
unset VIRTUAL_ENV

stamp="$(date +%Y-%m-%dT%H%M)"
logs="$AGX_PATHS_DOCUMENTS_DIR/logs"
mkdir -p "$logs"
log="$logs/regulation-ingest-$stamp.log"
exec >>"$log" 2>&1

status=0
step() {
  echo "=== $(date -Is) $*"
  if ! "$@"; then
    echo "!!! failed: $*"
    status=1
  fi
}

step uv run kbase basel-formulas
step uv run kbase ingest --target documents/manifest-regulation.yaml
step uv run kbase ingest --target documents/manifest-regulation-guidance.yaml
step uv run kbase verify
step uv run kbase stats
step uv run kbase eval --queries benchmarks/retrieval/queries-regulation.yaml \
  --label "night-$stamp-regulation" --details --output "$logs/eval-$stamp-regulation.json"
step uv run kbase eval --queries benchmarks/retrieval/queries.yaml --collection quant \
  --label "night-$stamp-quant" --output "$logs/eval-$stamp-quant.json"

summary="$(uv run python - "$logs" "$stamp" <<'EOF'
import json, sys
from pathlib import Path
logs, stamp = Path(sys.argv[1]), sys.argv[2]
lines = []
for name in ("regulation", "quant"):
    path = logs / f"eval-{stamp}-{name}.json"
    if not path.is_file():
        lines.append(f"- {name}: no report")
        continue
    m = json.loads(path.read_text())["overall"]
    part = f"- {name}: recall@10 {m['recall_at_10']:.3f}, MRR {m['mrr']:.3f}"
    if m.get("section_recall_at_10") is not None:
        part += f", paragraph recall@10 {m['section_recall_at_10']:.3f}"
    lines.append(part)
print("\n".join(lines))
EOF
)"
echo "=== $(date -Is) done, status=$status"
echo "$summary"

body="Night batch \`$stamp\` (infra/scripts/kbase-regulation-ingest.sh): status $([ $status = 0 ] && echo OK || echo FAILED).
$summary
Log: \`$log\`"
gh issue comment 66 --repo HadrienT/AgenticEnv --body "$body" || echo "could not comment on #66"
exit $status
