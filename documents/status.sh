#!/usr/bin/env bash
# Statut du corpus kbase : conversion PDF -> Markdown (MinerU) et ingestion Postgres.
set -uo pipefail

SRC_DIR=/srv/knowledge/documents/sources/all
RAW_DIR=/srv/knowledge/documents/raw
MINERU_PY=/home/hadriensuper/AgenticEnv/.mineru-venv/bin/python

echo "=== Conversion PDF -> Markdown ==="
"$MINERU_PY" -c "
import pypdf
from pathlib import Path

src = Path('$SRC_DIR')
raw = Path('$RAW_DIR')
done = {p.stem for p in raw.glob('*.md')}

total_pages = 0
done_pages = 0
remaining = []
for f in sorted(src.glob('*.pdf')):
    try:
        n = len(pypdf.PdfReader(str(f)).pages)
    except Exception:
        n = 0
    total_pages += n
    if f.stem in done:
        done_pages += n
    else:
        remaining.append((f.stem, n))

print(f'Documents : {len(done)}/{len(list(src.glob(chr(42)+chr(46)+chr(112)+chr(100)+chr(102))))}')
print(f'Pages     : {done_pages}/{total_pages} ({100*done_pages/total_pages:.1f}%)')
print()
print('Documents restants (id: pages) :')
for stem, n in remaining:
    print(f'  {stem}: {n}p')
" 2>/dev/null

echo ""
echo "=== Processus MinerU actifs ==="
ps aux | grep "bin/mineru -p" | grep -v grep | sed -E 's/.*sources\/all\/([^ ]+)\.pdf.*/  en cours: \1/' || echo "  (aucun)"

echo ""
echo "=== Ingestion Postgres (kbase) ==="
cd /home/hadriensuper/AgenticEnv
.venv/bin/kbase stats 2>&1 || echo "  (kbase stats indisponible)"
