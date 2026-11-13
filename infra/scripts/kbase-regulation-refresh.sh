#!/usr/bin/env bash
# WP21 monthly refresh of the regulation collection: fetch every source again (Basel
# Framework, EU Cellar, PRA Rulebook, eCFR, legislation.gov.uk, Federal Register, PDFs),
# read new formula images through MinerU, re-ingest what changed (ingestion skips a
# document whose file is unchanged, by sha256), check, evaluate, and comment the result
# on issue #71. Runs from the deployed checkout (`kbase-regulation-refresh.timer`).
#
#   systemctl --user start kbase-regulation-refresh.service   # run it now
#
# Network: polite fetching (3 s between requests, generic user agent), a few hundred
# requests in all. GPU: MinerU on new formula images and Basel chapter PDFs only.
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
log="$logs/regulation-refresh-$stamp.log"
exec >>"$log" 2>&1

status=0
step() {
  echo "=== $(date -Is) $*"
  if ! "$@"; then
    echo "!!! failed: $*"
    status=1
  fi
}
ingested() {  # documents re-ingested by one manifest (the others were unchanged)
  local manifest="$1" out
  echo "=== $(date -Is) ingest $manifest"
  if ! out="$(uv run kbase ingest --target "$manifest")"; then
    echo "$out"; echo "!!! failed: ingest $manifest"; status=1; return
  fi
  echo "$out"
  printf '%s' "$out" | uv run python -c \
    'import json,sys; t=sys.stdin.read(); d=json.loads(t[t.find("{"):]); print(d["documents_ingested"])' \
    > "$logs/.refresh-$stamp-$(basename "$manifest" .yaml)"
}

# Sources. Basel: every standard of the manifest, then its formulas (MinerU on the
# chapter PDFs, cached by content hash).
basel_args=()
for std in BCP CAP CRE DIS LCR LEV LEX MAR MGN NSF OPE RBC SCO SRP; do basel_args+=(--standard "$std"); done
step uv run kbase harvest-basel "${basel_args[@]}"
step uv run kbase basel-formulas
for catalog in configs/harvest/regulation-wave*.yaml; do
  step uv run kbase harvest-regulation --catalog "$catalog"
done
step uv run kbase regulation-formulas

for manifest in documents/manifest-regulation.yaml documents/manifest-regulation-guidance.yaml \
                documents/manifest-regulation-{intl,eu,uk,us}.yaml; do
  [ -f "$manifest" ] && ingested "$manifest"
done
step uv run kbase verify
step uv run kbase eval --queries benchmarks/retrieval/queries-jurisdictions.yaml \
  --label "refresh-$stamp-jurisdictions" --details --output "$logs/eval-$stamp-jurisdictions.json"
step uv run kbase eval --queries benchmarks/retrieval/queries-regulation.yaml --jurisdiction intl \
  --label "refresh-$stamp-basel" --output "$logs/eval-$stamp-basel.json"
step uv run kbase eval --queries benchmarks/retrieval/queries.yaml --collection quant \
  --label "refresh-$stamp-quant" --output "$logs/eval-$stamp-quant.json"

summary="$(uv run python - "$logs" "$stamp" <<'PY'
import json, sys
from pathlib import Path
logs, stamp = Path(sys.argv[1]), sys.argv[2]
lines = []
changed = {p.name.removeprefix(f".refresh-{stamp}-"): p.read_text().strip()
           for p in sorted(logs.glob(f".refresh-{stamp}-*"))}
lines.append("- re-ingested (changed) documents: " + ", ".join(f"{k} {v}" for k, v in changed.items()))
for p in logs.glob(f".refresh-{stamp}-*"):
    p.unlink()
for name in ("jurisdictions", "basel", "quant"):
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
PY
)"
echo "=== $(date -Is) done, status=$status"
echo "$summary"

# Sources the catalogues read must not leave the deployed checkout modified.
dirty="$(git status --porcelain -- documents/ configs/)"
[ -n "$dirty" ] && summary="$summary
- the checkout has changes to review (new manifest entries?): $(echo "$dirty" | tr '\n' ' ')"

body="Monthly regulation refresh \`$stamp\` (infra/scripts/kbase-regulation-refresh.sh): status $([ $status = 0 ] && echo OK || echo FAILED).
$summary
Log: \`$log\`"
gh issue comment 71 --repo HadrienT/AgenticEnv --body "$body" || echo "could not comment on #71"
exit $status
