# WP18 — arXiv harvest for the kbase

Grow the kbase from a few dozen hand-picked documents to thousands of arXiv papers on
the topics quant-modeling needs (numerical pricing, Monte Carlo, AAD, PDE, GPU, …),
without MinerU and without hand-written manifest entries.

## 1. Why not PDFs

MinerU OCRs each PDF page on the GPU, at 1 to 11 s per page while sharing both V100s
with `llama-server` (logs of 2026-09-04; one run was killed). A thousand 25-page papers
is days of GPU, and OCR'd equations are sometimes wrong, which is the worst failure for
a pricing corpus.

arXiv already converts the LaTeX sources of most papers to HTML with LaTeXML: natively
on `arxiv.org/html/<id>` for submissions since late 2023, and on
`ar5iv.labs.arxiv.org/html/<id>` for older ones. That HTML carries:

- the authors' LaTeX for every formula (`<math alttext="…">`), macros expanded by a
  real TeX emulator;
- equation numbers (`ltx_tag_equation`), so `kb.get_equation(doc_key, "12")` works;
- the section tree (`ltx_section`, `ltx_subsection`, …), tables, theorem and algorithm
  environments.

Converting it costs milliseconds of CPU per paper. Papers with no HTML on either host
are reported as `no_html` and left for the PDF path (#35).

## 2. Flow

```
profile YAML ─► arXiv API (Atom) ─► entries ─► filter (dates, already known ids)
            ─► fetch HTML (native, then ar5iv) ─► cache under documents_dir/arxiv/html
            ─► LaTeXML HTML → kbase Markdown ─► documents_dir/arxiv/md/<id>.md
            ─► manifest entries ─► documents/manifest-arxiv.yaml
then: kbase ingest --target documents/manifest-arxiv.yaml
```

`kbase harvest` stops at the manifest: ingestion stays the existing, idempotent
`kbase ingest`, so a harvest can be reviewed (or edited) before anything is embedded.

## 3. Profiles

A harvest profile (`configs/harvest/<name>.yaml`) lists arXiv search queries, each with
the kbase `topic` its papers get, a date window and a cap. Queries use the arXiv API
syntax (`cat:q-fin.CP AND abs:"Monte Carlo"`), so a profile is readable and
reproducible, and widening the corpus is a reviewed diff.

## 4. Politeness and resumption

- One request every 3 s across all arXiv hosts (arXiv API terms), a descriptive
  User-Agent, retries with backoff on 429/5xx.
- Every fetched HTML is cached; a rerun only fetches what is missing. Conversion is
  re-run from the cache, so improving the converter never re-downloads.
- arXiv ids already present in any manifest (`source_url`) are skipped, so the 20
  MinerU-parsed papers are not ingested twice.

## 5. Conversion rules

| LaTeXML | kbase Markdown |
|---|---|
| document title | `# Title` |
| abstract | `## Abstract` |
| section / subsection / subsubsection / paragraph | `##` / `###` / `####` / `#####`, with the number |
| numbered equation row | `$$` block closed by `$$ (n)` |
| unnumbered display | `$$` block, no number |
| `align` / `eqnarray` group | one block per row, cells joined |
| inline math | `$…$` from `alttext` |
| simple tabular | GFM pipe table, caption kept |
| figure | its caption as text |
| theorem, proof, algorithm | text, with its label |
| bibliography, footnote marks, navigation | dropped |

A converted paper is rejected (`low_quality`) if it has no section or under 1,500
characters of text: LaTeXML partial failures produce near-empty pages.

## 6. Out of scope

- PDF-only papers (→ #35, MinerU inside `kbase ingest`).
- Non-arXiv sources (SSRN has no API and forbids scraping).
- Relevance ranking of what to harvest beyond the profile's queries.

## 7. Acceptance

- `kbase harvest --profile <p>` produces Markdown files and a manifest that
  `kbase ingest` accepts without errors.
- A rerun with nothing new performs no HTML fetch.
- `kbase eval` on `queries-gaps.yaml` topics finds the harvested papers once their
  doc_keys are filled in.
