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

Upgrade procedure, **done by the maintainer**, not by an agent (issue #8: recreating a
container tears down a veth on `docker0`):

1. `just backup` (dump checked).
2. Pin `--branch v0.8.1` in `infra/docker/postgres/Dockerfile`, rebuild the image.
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

Licences: BIS and EUR-Lex allow reproduction with attribution; each entry records its
terms in `license`, checked per source before ingestion. English only: bge-m3 is
multilingual, so French questions still match English text.

### 5.2 Topics

`reg-capital-definition`, `reg-credit-sa`, `reg-irb`, `reg-ccr-sa-ccr`, `reg-ccr-imm`,
`reg-cva-capital`, `reg-frtb-sa`, `reg-frtb-ima`, `reg-securitisation`, `reg-op-risk`,
`reg-leverage`, `reg-liquidity`, `reg-large-exposures`, `reg-irrbb`, `reg-output-floor`,
`reg-disclosure`, `reg-model-risk`, `reg-data-aggregation`.

### 5.3 Versions

Each document version carries `valid_from` / `valid_until` (already in the schema and
the manifest). The BCBS framework publishes several versions of a chapter with their
effective dates: each becomes a version, not an overwrite. For the `regulation`
collection, `kb.search` defaults `valid_at` to today; the agent passes another date to
ask what applied then. Citations show the validity range.

## 6. Chunking and citations for regulatory text

### 6.1 Paragraph ids

The heading parser (`ingestion/parsers/headings.py`) recognises regulatory numbering in
addition to `2.1.1`:

- BCBS: `MAR21`, `MAR21.4`, footnotes `MAR21.4 FN3`
- EU: `Article 325c`, `Article 325c(2)`, `point (a)`

A parsed paragraph id is normalised (`MAR21.4`, `CRR:325c(2)`) and stored on the chunk:
`paragraph_ids text[]` on `kb.chunks` (migration `0008`), with a GIN index.

### 6.2 `regulatory` chunking strategy

`ChunkPolicy.strategy: regulatory`, selected per manifest entry (default for the
`regulation` collection):

- A chunk is one numbered paragraph, or several consecutive short paragraphs of the same
  section up to the target (400 tokens). A paragraph is never split unless it exceeds
  the max (700); a long one is split on its points `(a)`, `(b)`.
- Footnotes go with the paragraph that calls them, and tables with the paragraph that
  introduces them.
- The chunk text starts with its ids (`[MAR21.4–MAR21.6]`), so lexical search finds
  them. Queries are normalised the same way (`paragraph 21.4 of MAR` → `MAR21.4`)
  before lexical search.

### 6.3 Citations and enumeration

- `Citation` gains `paragraph_ids`, and `kb.search` results show them first. The id is
  stable across re-ingestion; UUIDs are not.
- `kb.list_paragraphs(doc_key, prefix=None, valid_at=None)` returns every paragraph
  of a document in order (id, first line, validity) and fetches one paragraph's full
  text with `kb.list_paragraphs(doc_key, prefix="MAR21.4")`. Search returns the top-k;
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

## 9. Delivery order

One PR each, `kbase eval` before and after each step.

1. **pgvector 0.8 + iterative scan** (§3.2). Independent; fixes the existing `topics`
   filter. Needs the maintainer for the container.
2. **Collections**: migration `0008` (`collection`, `paragraph_ids`), config, manifest,
   filter, `stats`.
3. **MCP**: required `collections`, `list_topics` by collection, agent profile line.
4. **Regulatory chunking**: heading patterns, `regulatory` strategy, citation
   `paragraph_ids`, query normalisation, `list_paragraphs`.
5. **First regulation wave**: the BCBS framework (`MAR`, `CRE`, `CAP` first) + model
   risk texts, `queries-regulation.yaml`, non-regression gate.
6. CRR3/EBA wave once step 5 holds.

## 10. Open questions

- BCBS framework ingestion: scrape the HTML chapter pages (clean structure, versions) or
  use the PDF export (one file, MinerU)? HTML is preferred if the pages can be fetched
  reliably.
- Should `quant` stay one collection, or should `performance-*` (C++/CUDA) become its
  own once it grows?
- Default `valid_at = today` for regulation: right for compliance, wrong for "what did
  Basel 2.5 require". Keep the default and make the parameter prominent in the tool
  description.
