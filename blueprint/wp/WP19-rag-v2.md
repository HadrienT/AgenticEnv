# WP19 — kbase RAG v2

Rework of the kbase pipeline before growing the corpus from ~40 to thousands of
documents (WP18). Every change below was measured on `kbase eval` (§6); configuration
in `configs/kbase-v2.yaml`.

## 1. What was wrong

| Finding | Effect |
|---|---|
| Each equation was its own chunk, holding only its LaTeX, and cut the prose around it | Text chunks had a median of ~150 tokens against an 800 target; 45% of chunks were bare formulas embedded without context |
| bge-m3 served with `--pooling mean` | bge-m3's dense retrieval is trained on the CLS token: every vector was degraded |
| MinerU headings flat (`## 2.1`, `## 2.1.1`, `## Bias` at one level), running headers repeated as headings | Section tree and section paths meaningless |
| Front and back matter ingested | Tables of contents, indexes, "Practice Questions", exercises, bibliographies: ~8% of the tokens, pure noise |
| Embeddings of the content alone | "generate two uniforms and…" does not say it is about Box-Muller in Glasserman |
| Reranker off, and quantized to 4 bits | Too slow on CPU (50 s/query); Q4 blurs the score gaps a cross-encoder resolves |
| No per-document cap | One long book could fill the whole top-k |
| HNSW `ef_search` left at 40 | Below `candidates_vector` (50): the scan returned fewer candidates than asked |
| Citations carried the section's UUID | The agent could not tell where a passage came from |
| `stochastic-optimization-notes` was a copy of Pham's book; test fixtures in the live corpus | Duplicate results |
| Re-ingesting a document kept the old version searchable; `sha256` unique made re-parsing an unchanged file fail | Re-chunking the corpus was impossible |

## 2. Parsing (`ingestion/parsers/headings.py`)

Heading levels are rebuilt from the numbering (`2.1.1` → level 4) when the Markdown
levels disagree with it (MinerU), kept otherwise (LaTeXML, hand-written Markdown).
Unnumbered headings hang under the last numbered one; those before any numbered
heading sit beside the shallowest numbered ones. A numbered heading seen twice is a
running header and is dropped; a heading with no word (`## 1, 3, 9, 5`) is text.

## 3. Curation (`ingestion/curation.py`)

Sections whose whole title (leading number removed) matches `curation.drop_sections`
are dropped with their subtree, except numbered subsections, which are content. A
manifest entry can add `exclude_sections` for one document. The document title
(level 1) is never dropped: MinerU sometimes nests a whole book under `# Front matter`.

Basic chapters are kept on purpose: they are the best source for basic questions, and
reranking plus the per-document cap keep them from crowding out specialised passages.

## 4. Chunking (`SectionChunker`, `strategy: section`)

- Chunks follow the section tree and carry equations and tables inline, in reading
  order (`$$ … $$ (n)`); each equation is still recorded in `kb.equations`, so
  `kb.get_equation(doc, "2.24")` keeps working.
- A section's heading opens its first chunk. Target 400 model tokens (estimated at
  4 characters per token: whitespace words undercount LaTeX), max 700, overlap 50
  within a section; a chunk under 120 tokens absorbs the next sibling section of the
  same chapter instead of standing alone.

## 5. Embedding and retrieval

- **Contextual reranking**: the cross-encoder reads each chunk as `document title /
  section path / content`. The same header on the *embedding* side was measured too and
  dropped (§8): repeated on every chunk of a book, it made them look alike.
- **bge-m3 with CLS pooling**, on GPU (`infra/scripts/run-embed-server.sh`).
  Qwen3-Embedding-0.6B was tried but does not fit in the VRAM left beside the main
  model (decoder: KV cache + compute buffers).
- **Reranker** bge-reranker-v2-m3 **Q8_0** on GPU, over the 100 best fused candidates.
- **Per-document cap**: at most 3 chunks of one document in a result, backfilled if too
  few documents remain.
- `hnsw.ef_search` set per query (200); candidates 100 vector + 100 lexical.
- An English-stemmed full-text column was tried and brought nothing (identical scores):
  not shipped; lexical search stays `simple`, which keeps SABR, SOFR, CVA intact.
- Citations carry `section_path` (`2 Generating Random Numbers › 2.3.2 Box-Muller`).

## 6. Evaluation

`benchmarks/retrieval/queries.yaml` (84 hand-written queries, document-level) and
`queries-sections.yaml` (143 passage-level queries generated from seeded sections by the
local LLM, paraphrased, see `make_section_queries.py`). A passage hit is a chunk of the
expected document carrying the expected section title. Results: §8.

## 7. Operations

- `kbase delete --doc-key …` removes documents and everything derived from them.
- Re-ingestion replaces the previous version in the same transaction.
- Moving to v2 means: deploy the embed/rerank script, re-ingest with
  `--force-reparse`, switch `AGX_KBASE_CONFIG`, `agentmem reembed` (agentmem shares the
  embedding server, and its vectors change with the pooling).

## 8. Results

Same queries, 2026-11-09. "Passage" = 143 generated queries, hit = right document and
right section; "document" = the 84 hand-written queries of `queries.yaml`.

| Configuration | Doc R@5 | Doc MRR | Doc nDCG@10 | Passage R@5 | Passage R@10 | Passage MRR | p50 |
|---|---|---|---|---|---|---|---|
| Production before WP19 (structural chunks, mean pooling, no reranker) | 0.92 | 0.72 | 0.68 | 0.58 | 0.73 | 0.37 | 0.4 s |
| v2 without reranker | 0.99 | 0.81 | 0.77 | 0.83 | 0.88 | 0.71 | 0.2 s |
| v2, contextual embeddings + reranker (50) | 0.99 | 0.85 | 0.81 | 0.91 | 0.93 | 0.83 | 1.3 s |
| **v2 as shipped** (raw embeddings, contextual reranker, 100 candidates) | **1.00** | **0.85** | **0.83** | **0.90** | **0.93** | **0.82** | 2.3 s |

Variants (passage R@5 / MRR, against 0.91 / 0.83 for the 50-candidate run):

| Change | Result | Kept |
|---|---|---|
| No reranker | 0.81 / 0.69 | no: the cross-encoder is worth 12 points of passage MRR |
| No per-document cap | 0.92 / 0.83, but document nDCG 0.75 instead of 0.81 | cap 3 kept: diverse sources for nearly no cost |
| Cap 2 | 0.89 / 0.82 | no |
| English stemming | identical | no |
| 30 candidates | 0.90 / 0.83, document nDCG 0.79 | no |
| 100 candidates | 0.91 / 0.83, document R@5 1.00, nDCG 0.83 | yes (latency 2.4 s) |
| Contextual embeddings, no reranker | 0.81 / 0.69 vs 0.83 / 0.71 raw | raw embeddings |
| Contextual reranker over raw embeddings | 0.91 / 0.82, passage R@10 0.95, document MRR 0.85 | yes |

Bigger models, tested with the main LLM stopped to free both V100s:

| Test | Result |
|---|---|
| Passage recall of the first stage (bge-m3, before reranking) | 0.90 at 10, 0.96 at 30, 0.98 at 50, **0.986 at 100**: the right passage is almost always among the 100 candidates, so a better embedder can win at most ~1.4 points today; the reranker is the bottleneck |
| Qwen3-Embedding-8B (1,383 tok/s on a V100) | not run on the corpus, given the ceiling above; worth re-measuring once thousands of papers make the first stage harder (`embeddings.truncate_dim` keeps its first 1024 dimensions) |
| Qwen3-Reranker-0.6B (official llama.cpp conversion) | passage R@5 0.86 / MRR 0.77 vs 0.90 / 0.82 for bge-reranker, and 5.5 s per query: no |
| Qwen3-Reranker-4B (community GGUF) | broken conversion (scores of 1e-27, wrong order); the local converter cannot rebuild it |

The remaining passage misses are mostly generic questions several books answer (a
Monte Carlo versus quasi-Monte Carlo question returns Glasserman before the paper the
query was generated from). Ingesting the corpus takes 9.5 minutes on one V100 (vs ~7 h
estimated on the CPU).
