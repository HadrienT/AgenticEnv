# WP20 — kbase collections and the regulation corpus

Split the knowledge base into **collections** that the agent must choose when it
searches, then add a second corpus: banking regulation (BCBS, CRR/CRD, EBA, model risk
guidance). The regulation corpus is the groundwork for a later use: checking that the
quant-modeling codebase meets the regulatory requirements it implements (§7).

Tracking issue: #66.

## 1. Why

| Finding | Effect |
|---|---|
| One shared ranking for every document | The two domains share vocabulary: *CVA* (27 pricing papers in `cva-xva` vs SA-CVA/BA-CVA capital), *exposure*, *sensitivities*, *Monte Carlo* (IMA, EEPE), *capital*. Regulatory passages would crowd quant questions, and the reverse. The reranker only reorders the candidates it is given |
| Every filter of `kb.search` is optional | A local model mostly leaves them out, so filters exist but are not used |
| pgvector **0.7.4**, HNSW index on all of `kb.chunk_embeddings` | HNSW filters *after* the graph scan: it returns about `ef_search` (200) neighbours, then the `WHERE` drops those outside the filter. With a selective filter, few or no candidates survive, and nothing reports it. This already affects `topics` today and gets worse as the corpus grows |
| Regulatory texts cite by paragraph (`MAR21.4`, `CRE52.12`, `Article 325c(2)`) | The structural chunker splits on sections by size; citations carry a section path, not a paragraph id. A compliance review needs the paragraph |

Measured on 2026-11-12: 525 documents (503 papers, 19 books, 3 documentation), 50,100
chunks; Postgres 16.15, pgvector 0.7.4; lexical config `simple` keeps `MAR21.4` and
`CRE52.12` as single tokens, but `paragraph 21.4 of MAR` does not match them.

## 2. Collections

A collection is a corpus with its own scope, described in one line. Two to start:

| Collection | Content |
|---|---|
| `quant` | The current corpus: pricing models, numerical methods, XVA, C++/CUDA performance |
| `regulation` | Prudential regulation and supervisory guidance: BCBS, CRR/CRD, EBA, model risk |

- **Schema** (migration `0008`): `collection text not null` on `kb.documents`, backfilled
  to `quant`, with an index. The value must be one of the collections declared in the
  kbase config. A table is not needed while collections are only a name and a
  description.
- **Config** (`configs/kbase*.yaml`): `collections: {quant: {description: …},
  regulation: {description: …}}`. The descriptions feed the MCP tool schema (§4).
- **Manifest**: a `collection:` key per entry, and a top-level default per manifest file
  (`documents/manifest-regulation.yaml` sets `collection: regulation` once). Missing
  everywhere = ingestion error, never a silent default.
- **`kbase stats` / `list_topics`** report counts per collection.

Topics stay a flat string; regulation topics are prefixed `reg-` so they never collide
with quant topics.

## 3. Retrieval

### 3.1 Filter

`RetrievalFilters.collections: list[str] | None`, translated in `filters.py` as
`d.collection = ANY(:collections)`. `None` means the whole base and stays available to
the CLI and `kbase eval`; the MCP tool does not allow it (§4). Fusion, reranking and the
per-document cap are unchanged.

### 3.2 Filtered HNSW (prerequisite)

Upgrade pgvector to **0.8.x** and enable iterative index scans per query:

```sql
SET LOCAL hnsw.iterative_scan = relaxed_order;
SET LOCAL hnsw.max_scan_tuples = 20000;   -- bound on the extra work, to tune
```

With iterative scans, HNSW keeps walking the graph until it has `LIMIT` rows that pass
the filter. `relaxed_order` can return rows slightly out of order, so the vector query
is wrapped in a materialized CTE and sorted again on the distance.

`retrieval.hnsw_iterative_scan` / `hnsw_max_scan_tuples` in the kbase config turn it on
(set in `kbase-v2.yaml`). The retriever reads `extversion` once: on pgvector < 0.8 it
sets nothing, search keeps working as before, and every filtered result carries a
warning, so the code can ship before the database is upgraded.

Upgrade procedure, **done by the maintainer**, not by an agent (issue #8: recreating a
container tears down a veth on `docker0`):

1. `just backup` (dump checked).
2. Rebuild the image (`infra/docker/postgres/Dockerfile` pins `v0.8.7`, released
   2026-10-01).
3. Recreate **only** `agenticenv-postgres` (`docker compose -f infra/docker/compose.yaml
   up -d postgres`). The data volume is kept.
4. `ALTER EXTENSION vector UPDATE;` in each database (`agenticenv`, `agenticenv_test`).
   The HNSW index does not need a rebuild.

Fallback if the upgrade is refused: a `collection` column copied onto
`kb.chunk_embeddings` and one partial HNSW index per collection
(`WHERE collection = 'regulation'`), one query per collection merged in Python. This
costs a column to keep in sync and N index scans for a multi-collection query; the
upgrade is preferred.

Measure `kbase eval` before and after the upgrade with no collection filter: scores
must not change. Then measure with `topics=[…]` on a narrow topic: recall should rise.

## 4. MCP surface

- `kb.search` takes `collections: list[Literal["quant", "regulation"]]`, **required**,
  at least one item. The enum and its descriptions come from the config, so the JSON
  schema the model sees reads, for example, *"regulation: BCBS, CRR/CRD, EBA texts:
  capital, market/counterparty/credit risk rules, model risk"*. A question that spans
  both domains passes both (*"how should EEPE be computed for CRE53, and how do we
  simulate it"*).
- `kb.list_topics` groups topics, asset classes and years by collection, with
  document counts.
- `kb.list_paragraphs` (new, §6.3) and `kb.get_document` work on any collection.
- The agent profiles in `agents/` get one line: choose the collection first, call
  `list_topics` when unsure.

**Why not a second MCP server.** Routing by tool name would work, but it would duplicate
the engine, the config and the tests. It would also add tools to the context of a local
model, and cross-domain questions would take two calls whose rankings cannot be
compared. A required parameter gives the same forced choice from a single engine. If
measurements (§8) show the model picks the collection badly, the same server can expose
thin `search_quant` / `search_regulation` wrappers without changing the engine.

## 5. Regulation corpus

### 5.1 Sources (first wave)

| Source | Format | Notes |
|---|---|---|
| BCBS consolidated Basel Framework (bis.org/basel_framework): `CAP`, `RBC`, `CRE`, `MAR`, `LEV`, `LCR`, `NSF`, `LEX`, `SRP`, `DIS`, `OPE` | HTML, one page per chapter, numbered paragraphs, effective dates per version | Primary source. One document per chapter (`bcbs-mar21`), `doc_type: standard` |
| BCBS standalone texts not in the framework, or kept for history: d457 (FRTB 2019), d424 (Basel III finalisation), d279 (SA-CCR), d507 (CVA 2020), d239 (BCBS 239) | PDF → MinerU | `valid_until` set when superseded |
| EU CRR3 / CRD6 (EUR-Lex, English) | HTML | One document per Part/Title; articles and points as paragraph ids |
| EBA RTS/ITS/GL tied to the above (FRTB-SA, IMA, SA-CCR, IRRBB) | PDF | |
| Model risk: Fed/OCC SR 11-7, ECB guide to internal models, PRA SS1/23 | PDF | The texts closest to code review (§7) |

What the Basel Framework site gives (checked 2026-11-12): one page per chapter at
`/committees/bcbs/basel-framework/standard/<std>/<nn>/inforce/<date>/published/<date>`,
so the in-force date is in the URL; each paragraph is a `div.framework-paragraph` whose
`id` is its number (`21.4`), headings are `h4`, footnotes are a table after the
paragraph. **Formulas are SVG images of glyph outlines, with no text or `alt`**: the HTML
cannot give them. The converter writes a `[formula: <image>]` placeholder; the formulas
need the per-standard PDF through MinerU (step 5b, §9).

Licences: BIS and EUR-Lex allow reproduction with attribution; each entry records its
terms in `license`, checked per source before ingestion. English only: bge-m3 is
multilingual, so French questions still match English text.

### 5.2 Topics

`reg-capital-definition`, `reg-credit-sa`, `reg-irb`, `reg-ccr-sa-ccr`, `reg-ccr-imm`,
`reg-cva-capital`, `reg-frtb-sa`, `reg-frtb-ima`, `reg-securitisation`, `reg-op-risk`,
`reg-leverage`, `reg-liquidity`, `reg-large-exposures`, `reg-irrbb`, `reg-output-floor`,
`reg-disclosure`, `reg-model-risk`, `reg-data-aggregation`.

### 5.3 Versions

Each document carries `valid_from` / `valid_until` (already in the schema and the
manifest). Re-ingesting a `doc_key` replaces its previous version (WP19), so versions of
a chapter that must coexist get their own `doc_key`: `bcbs-mar21` for the version in
force, `bcbs-mar21-2019-01-01` (with `valid_until`) for an older one kept for history. For the `regulation`
collection, `kb.search` defaults `valid_at` to today; the agent passes another date to
ask what applied then. Citations show the validity range.

## 6. Chunking and citations for regulatory text

### 6.1 Paragraph ids (`kbase/regulatory.py`)

The regulation converters write **each paragraph as its own heading** (`### MAR21.4`),
under the chapter's own headings. A section whose title is a paragraph id makes the
chunks covering it carry that id:

- Basel: `MAR21.4`, `CRE52.12a` (the 14 standards of the framework)
- EU: `Article 325c` (points and sub-paragraphs stay in the text)

`paragraph_ids text[]` on `kb.chunks` (migration `0008`), with a GIN index.

### 6.2 Chunking: the `section` strategy, unchanged

Implemented without a new strategy: with paragraphs as sections, `SectionChunker`
already does what was asked. A paragraph's heading opens its first chunk; a section
boundary closes a chunk once it has `min_tokens`, so short paragraphs merge with the
next one and a long paragraph is split at sentences, every part keeping its id.
Footnotes are written inside the paragraph that calls them. Only the first chunk of a
split paragraph holds the id in its text; all its chunks hold it in `paragraph_ids`.

Lexical search normalises spelled-out references first (`paragraph 21.4 of MAR`,
`MAR 21.4` → `MAR21.4`), the token the heading puts in the index. The embedding and the
reranker still see the question as written.

### 6.3 Citations and enumeration

- `Citation` gains `paragraph_ids`, and `kb.search` results show them first. The id is
  stable across re-ingestion; UUIDs are not.
- `kb.list_paragraphs(doc_key, prefix=None)` returns every paragraph of a document in
  order (id, section path, first line) with the document's validity, and the full text
  of the chunks holding the paragraphs that match `prefix` (`MAR21.4`, or `MAR21` for a
  chapter; at most 40 chunks, `truncated` says when there were more). Search returns the top-k;
  a review must see **all** the requirements of a chapter (§7).

## 7. Target use: compliance review of a codebase

The next step after this WP: an agent checks that quant-modeling implements a
regulatory method correctly (e.g. SA-CCR add-ons, FRTB-SA sensitivities and correlation
scenarios, the CVA capital formula). This WP only provides what the review needs from
the knowledge base:

1. **Exhaustive requirements**: `list_paragraphs` over a chapter, not a top-k search
   that can miss a paragraph.
2. **Citable requirements**: a stable paragraph id and its validity range, so a
   finding reads "`MAR21.43` (in force since 2023-01-01) is not met by
   `frtb/sa/curvature.cpp:120`".
3. **Cross-domain search**: `collections=["regulation", "quant"]` for "what the text
   requires" next to "how it is usually computed".

Out of scope, for a follow-up WP: the review workflow itself (requirement → code
location → status matrix, stored and versioned), and linking to `codeintel` and
`qmharness` to check numbers against the regulatory examples.

## 8. Evaluation

- `benchmarks/retrieval/queries-regulation.yaml`, passage-level, with categories:
  `exact-id` (`MAR21.4`), `paraphrase`, `french`, `version` (with `valid_at`), and
  `cross-domain-trap`: questions whose words exist in both collections (CVA capital vs
  CVA pricing, IMA vs Monte Carlo pricing), scored in **both** directions.
- **Non-regression gate**: with the regulation corpus ingested, the quant sets
  (`queries.yaml`, `queries-sections.yaml`) run with `collections=["quant"]` must score
  within noise of the WP19 baseline (recall@10, MRR, nDCG). The same sets run without a
  filter measure how much the corpora interfere.
- **Routing**: a handful of agent-bench prompts check that the local model picks the
  right collection. If it often picks wrong, add the two wrapper tools (§4).

### 8.1 Results (2026-11-12, `kbase-v2.yaml`, pgvector 0.7.4)

Quant sets, before and after ingesting the 47 Basel chapters (1,968 chunks, ~4% of
the base). Files in `benchmarks/retrieval/results/2026-11-12-wp20-*.json`.

| Set | Run | recall@5 | recall@10 | MRR | nDCG@10 | passage recall@10 | passage MRR |
|---|---|---|---|---|---|---|---|
| `queries.yaml` (84) | before | 0.810 | 0.893 | 0.629 | 0.565 | | |
| | after, `collections=[quant]` | 0.810 | **0.893** | 0.629 | 0.565 | | |
| | after, no filter | 0.810 | **0.869** | 0.623 | 0.556 | | |
| `queries-sections.yaml` (143) | before | 0.958 | 0.986 | 0.878 | 0.904 | 0.923 | 0.792 |
| | after, `collections=[quant]` | 0.958 | 0.986 | 0.878 | 0.904 | 0.923 | 0.792 |
| | after, no filter | 0.958 | 0.986 | 0.878 | 0.904 | 0.923 | 0.792 |

- **Gate met**: with the collection filter, the quant scores are unchanged.
- **The interference is real**: without a filter, 47 chapters already cost 2.4 points
  of recall@10 on the document-level set (questions on CVA, exposure, Monte Carlo, the
  shared vocabulary of §1). The passage-level set, made of narrow numerical questions,
  is not affected.
- Still on pgvector 0.7.4: `quant` is 96% of the base, so post-filtering loses little
  here. The upgrade matters for the small collection (`regulation`) and narrow topics.

`queries-regulation.yaml` (26 queries):

| Category | n | recall@10 | MRR | paragraph recall@10 | paragraph MRR |
|---|---|---|---|---|---|
| exact-id | 4 | 1.00 | 1.00 | 1.00 | 0.88 |
| paraphrase | 15 | 1.00 | 0.91 | 0.80 | 0.68 |
| french | 3 | 1.00 | 0.57 | 0.33 | 0.36 |
| cross-domain-trap | 4 | 1.00 | 0.65 | 0.50 (2 with paragraphs) | 0.50 |
| overall | 26 | 1.00 | 0.85 | 0.75 | 0.66 |

- The right chapter is always in the top 10, in the top 5 for 96% of the queries.
- The two traps that expect quant papers (CVA pricing, CVA exposure) return quant
  papers first, never Basel text, even when both collections are searched.
- An id written inside a sentence (`What does MAR33.3 require?`) was lost: the
  any-term lexical fallback only kept alphabetic words. Fixed (`paragraph_tokens`);
  exact-id passage recall went from 0.75 to 1.00.
- What is left: (1) paragraphs that are mostly formulas (`CRE31.5`, the IRB risk-weight
  function, is four placeholders): step 5b; (2) the per-document cap (3 chunks) leaves
  little room to pick the right paragraph inside the one chapter a regulatory question
  is about; (3) French questions rank the passage lower (bge-m3 across languages, the
  reranker on English text).

## 9. Delivery order

Steps 1–5a shipped together in one PR (#67); `kbase eval` before and after.

1. **pgvector 0.8 + iterative scan** (§3.2). Code done (probe + warning on 0.7.4,
   Dockerfile pins v0.8.7). **Left: image rebuild and container recreation, by the
   maintainer.**
2. **Collections**: done; migration `0008` applied to the real database on 2026-11-12
   (after a dump), the 525 existing documents in `quant`.
3. **MCP**: done (required `collections`, `list_topics` by collection, `list_paragraphs`,
   agent profiles and prompts).
4. **Paragraph ids**: done (§6), without a new chunking strategy.
5. a. **Basel Framework, MAR + CRE + CAP**: `kbase harvest-basel`, 47 chapters, 1,846
      paragraphs, 1,968 chunks, ingested 2026-11-12; `queries-regulation.yaml`;
      results §8.1.
   b. **Formulas** (409 placeholders; MAR21 alone has 188, then CRE99, MAR50, CRE52,
      CRE31: the chapters a code review needs). Per-chapter PDF
      (`/committees/bcbs/basel-framework/<id>/chapter.pdf`) through MinerU, formulas
      matched to the placeholders in reading order.
   c. Remaining standards (`RBC`, `SRP`, `OPE`, `LEV`, `LEX`, `LCR`, `NSF`, `DIS`, …):
      one `harvest-basel --standard …` run each.
   d. Model risk texts (SR 11-7, ECB guide to internal models, PRA SS1/23): PDF.
6. CRR3/EBA wave once step 5 holds.

## 10. Open questions

- ~~BCBS framework: HTML or PDF?~~ HTML for the text and structure (done); the PDF only
  for the formulas (step 5b).
- Should `quant` stay one collection, or should `performance-*` (C++/CUDA) become its
  own once it grows?
- Default `valid_at = today` for regulation: right for compliance, wrong for "what did
  Basel 2.5 require". Keep the default and make the parameter prominent in the tool
  description.
