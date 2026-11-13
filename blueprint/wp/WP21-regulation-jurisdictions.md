# WP21 — Regulation by jurisdiction (US, EU, UK)

Status: design, 2026-11-13. Follows WP20 (collections, Basel Framework corpus).
Tracking: GitHub issue "WP21: regulation by jurisdiction".

## 1. Why

The `regulation` collection holds the Basel Framework (BCBS) and four model-risk guides.
Basel is not law: each jurisdiction transposes it with its own text, options, numbers
and calendar, and the rules a bank must implement are those of its jurisdiction:

| | Binding market/credit/CCR/CVA rules | Calendar (checked 2026-11-13) |
|---|---|---|
| EU | CRR (Regulation 575/2013 as amended by CRR3, 2024/1623) + EBA RTS/ITS adopted as Commission Delegated Regulations | CRR3 applies since 2025-01-01; FRTB own funds requirements from 2027-01-01 after two postponements (Delegated Regulations 2024/2795, 2025/1496), with targeted multipliers and operational relief (Delegated Regulation 2026/1221 of 2026-06-04); CRR2 methods until then |
| UK | PRA Rulebook, CRR firms (Basel 3.1 rules restated as PRA rule parts) | Basel 3.1 from 2027-01-01 (PS1/26); market risk IMA from 2028-01-01; CP9/26 consults on IMA changes |
| US | 12 CFR 217 (Fed, Regulation Q; OCC 12 CFR 3 and FDIC 12 CFR 324 are the same rule) | 2013 rule still binding; Basel III endgame re-proposal of 2026-03-19 (expanded risk-based approach) pending, comments closed 2026-06-18 |

The base today cannot say which jurisdiction a text belongs to (SR 26-2 is American,
SS1/23 British, the ECB guide European, nothing records it), and an agent answering
"how is the SA-CCR add-on computed" may mix the Basel paragraph with a rule it does not
match.

Scope asked by the maintainer: equity derivatives, credit, XVA, and **what can be
implemented**: rules that turn into a calculation, a data requirement or a model
control. The whole of each rulebook is out of scope (liquidity, governance, reporting
templates, remuneration, recovery).

## 2. The `jurisdiction` dimension

`kb.documents.jurisdiction text NULL`, checked in (`intl`, `eu`, `us`, `uk`):

- `intl`: BCBS standards and other international texts (IOSCO/BCBS margin framework).
- `eu`, `us`, `uk`: texts of that jurisdiction's legislator or supervisors.
- NULL for every non-regulatory document. A CHECK makes it **required for the
  `regulation` collection** and forbidden elsewhere, so a manifest cannot add an
  unlabelled regulatory text.

Migration `0009` adds the column, backfills `intl` on the 123 Basel chapters and the
right value on the four guides, then adds the constraints.

Why a column and not one collection per jurisdiction: the vocabulary is shared, and a
common question is comparative ("what does Basel say and how did the EU transpose it").
Separate collections would bring back the problem WP20 §4 rejected: several calls whose
rankings cannot be compared.

### 2.1 Document types

`doc_type` gains three values so the agent can tell binding text from guidance:

| `doc_type` | Meaning | Examples |
|---|---|---|
| `standard` | international standard, not binding by itself | Basel Framework chapters |
| `law` | binding rules | CRR articles, EU Delegated Regulations (RTS), 12 CFR 217, PRA rule parts |
| `guidance` | supervisory expectations | SR 26-2, SS1/23, ECB guide, EBA guidelines |
| `proposal` | consultation or proposed rule, not in force | US 2026 re-proposal, PRA CP9/26 |

The four guides move from `standard` to `guidance`.

### 2.2 Validity and texts that apply later

WP20 §5.3 defaults `valid_at` to today for the `regulation` collection. With the UK
Basel 3.1 rules applying on 2027-01-01 and the EU FRTB the same day, the texts banks are
implementing now would be invisible until then. New default when `valid_at` is not
given: **not expired** (`valid_until IS NULL OR valid_until >= today`). Texts in force and
texts that apply later are both returned; superseded ones are not. Each citation carries
`valid_from`, and a result whose `valid_from` is in the future gets a note ("applies from
2027-01-01"). An explicit `valid_at` keeps its exact meaning (what applied that day).

Where the current and the upcoming text both matter (UK market risk until 2026-12-31,
then Basel 3.1), both versions are ingested under distinct `doc_key`s with their ranges.

## 3. Retrieval and MCP surface

- `RetrievalFilters.jurisdictions: list[Jurisdiction] | None`. The filter only restricts
  regulatory documents: the predicate is
  `(d.collection <> 'regulation' OR d.jurisdiction = ANY(:jurisdictions))`, so a
  cross-domain question (`collections=["quant", "regulation"]`) keeps its quant results.
- `kb.search` takes `jurisdictions: list[Literal["intl", "eu", "us", "uk"]]`, optional.
  The tool description lists each jurisdiction with what the base holds for it, built
  from the config like the collections (`jurisdictions:` in `kbase-v2.yaml`). The
  description must not promise texts that are not ingested: it is updated with each
  ingestion wave, and a test checks that every configured jurisdiction has documents in
  the evaluation fixtures.
- Guidance in the description: name the jurisdiction the question is about; add `intl`
  for the Basel reference; when the question names none, search all and say which
  jurisdiction each rule comes from.
- `Citation.jurisdiction` and `doc_type` are returned with every result, and the
  formatted citation starts with the jurisdiction (`[EU, law] CRR Article 274(2)`).
- `kb.list_topics` groups by collection, then jurisdiction, with topics and counts.
- **New `kb.list_documents`** (`collection`, optional `jurisdiction`, `topic`,
  `doc_type`): doc_key, title, doc_type, validity. Today the agent only learns doc_keys
  from search results, and `kb.list_paragraphs` needs one.
- CLI `kbase search` / `kbase eval` take `--jurisdiction`; evaluation queries may set
  `jurisdictions`.

## 4. Paragraph ids per jurisdiction

| Jurisdiction | Source unit | Paragraph id | Example |
|---|---|---|---|
| intl | Basel chapter paragraph | `<STD><ch>.<n>` | `MAR21.4` |
| eu | CRR / Delegated Regulation article, numbered paragraph | `Article <n>` / `Article <n>(<p>)` | `Article 274(2)` |
| uk | PRA rule part: CRR-style articles, or numbered rules | `Article <n>(<p>)` / `<rule>` | `Article 325c(2)`, `2.1` |
| us | CFR section, paragraph path | `§ <part>.<sec>(<a>)(<1>)…` | `§ 217.132(c)(1)` |

`Article 274(2)` exists in the EU CRR and in the PRA CCR part: ids are unique within a
document, and the jurisdiction filter or the doc_key tells them apart. Lexical
normalisation learns `Art. 274(2)`, `article 274 paragraph 2` and `12 CFR 217.132(c)`,
`section 217.132`.

## 5. Source catalogue (scope: equity derivatives, credit, XVA)

Priority **P1** = the rules a pricing or risk library implements (capital calculations,
margin, valuation adjustments); **P2** = what frames them (definitions, boundary,
model approval, proposals).

### 5.1 EU

Source: the Publications Office Cellar API (`publications.europa.eu/resource/celex/<celex>`
with `Accept: application/xhtml+xml`), which serves the consolidated text. EUR-Lex itself
answers scripts with an anti-bot challenge.

| P | Text | Content kept | doc_key |
|---|---|---|---|
| P1 | CRR consolidated, Part Three Title IV (Art. 325–377) | market risk: FRTB alternative standardised (SBM, DRC, RRAO), IMA, simplified SA, legacy CRR2 methods | `eu-crr-p3-t4-*` per chapter |
| P1 | CRR Part Three Title II Chapter 6 (Art. 271–311) | counterparty credit risk: SA-CCR, simplified SA-CCR, OEM, IMM, CCP exposures | `eu-crr-p3-t2-c6-*` per section |
| P1 | CRR Part Three Title VI (Art. 381–386) | CVA risk: SA-CVA, BA-CVA, simplified | `eu-crr-p3-t6` |
| P1 | CRR Art. 105 + Delegated Regulation 2016/101 | prudent valuation, AVAs (incl. unearned credit spread, investing and funding costs) | `eu-crr-art105`, `eu-rts-2016-101` |
| P1 | Delegated Regulation 2016/2251 (EMIR) | margin for non-centrally cleared OTC derivatives: IM models, thresholds, collateral, haircuts | `eu-rts-2016-2251` |
| P1 | EBA RTS on SA-CCR (Delegated Regulation 2021/931) | primary risk driver, supervisory delta for options, risk categories | `eu-rts-2021-931` |
| P1 | EBA FRTB RTS adopted as Delegated Regulations (risk factor modellability, residual risks, gross JTD, liquidity horizons, back-testing and PLA) | list to establish from the EBA FRTB page at harvest time | `eu-rts-<year>-<n>` |
| P2 | CRR Part Three Title II Chapters 2–4 (Art. 111–241) | credit risk SA, IRB, credit risk mitigation (counterparty and issuer side) | per chapter |
| P2 | CRR Art. 4 (definitions), Art. 92 (own funds, output floor), Art. 102–106 (trading book) | | |
| guidance | ECB guide to internal models (already in) | | |

### 5.2 UK

Source: the PRA Rulebook, which shows each part at a given date, including future ones
(`/pra-rules/<part>/<dd-mm-yyyy>`).

| P | PRA rule part (CRR firms) | Version(s) | doc_key |
|---|---|---|---|
| P1 | Market Risk: General Provisions (CRR) | 2027-01-01 | `uk-pra-mr-general` |
| P1 | Market Risk: Advanced Standardised Approach (CRR) | 2027-01-01 | `uk-pra-mr-asa` |
| P1 | Market Risk: Simplified Standardised Approach (CRR) | 2027-01-01 | `uk-pra-mr-ssa` |
| P1 | Market Risk: Internal Model Approach (CRR) | from 2028-01-01 | `uk-pra-mr-ima` |
| P1 | Counterparty Credit Risk (CRR) | current + 2027-01-01 | `uk-pra-ccr`, `uk-pra-ccr-2027` |
| P1 | Credit Valuation Adjustment Risk (replaces the CRR part on 2027-01-01) | 2027-01-01 | `uk-pra-cva-2027` |
| P1 | UK EMIR margin RTS (onshored 2016/2251, legislation.gov.uk) | current | later wave (another format) |
| P1 | UK prudent valuation (onshored 2016/101) | current | later wave: the Rulebook's "Valuation" part is the Solvency II one, for insurers |
| P2 | UK CVA until 2026-12-31 (onshored CRR, legislation.gov.uk) | current | later wave: the PRA's current CVA (CRR) part is nearly empty |
| P2 | Trading Book (CRR) | 2027-01-01 | `uk-pra-trading-book` |
| P2 | Credit Risk: General Provisions / Standardised Approach / IRB / Credit Risk Mitigation (CRR) | 2027-01-01 | `uk-pra-cr-*` |
| P2 | Required Level of Own Funds (CRR) (output floor) | 2027-01-01 | `uk-pra-own-funds-level` |
| P2 | CP9/26, IMA adjustments | proposal | `uk-pra-cp9-26` |
| guidance | SS1/23 model risk (already in) | | |

### 5.3 US

Source: the eCFR versioner API (`ecfr.gov/api/versioner/v1/full/<date>/title-<n>.xml`,
compressed responses required), structured XML per section with the paragraph markers;
the Federal Register API for proposals.

| P | Text | Content kept | doc_key |
|---|---|---|---|
| P1 | 12 CFR 217 Subpart F (§ 217.201–217.212) | market risk: VaR, stressed VaR, specific risk, IRC, CRM, securitisation positions | `us-cfr-217-f-<sec>` |
| P1 | 12 CFR 217.132–217.133 (Subpart E) | counterparty credit risk: SA-CCR, IMM, collateral haircuts, CVA (advanced approaches), cleared transactions | `us-cfr-217-132`, `-133` |
| P1 | 12 CFR 217.34, 217.35, 217.37 (Subpart D) | OTC derivatives under the standardised approach (CEM/SA-CCR), cleared transactions, collateralised transactions | `us-cfr-217-34`… |
| P1 | 12 CFR 237 Subpart A (Fed swap margin rule; OCC 12 CFR 45 identical) | margin for non-cleared swaps of prudentially regulated swap entities | `us-cfr-237-a` |
| P1 | 17 CFR 23.150–23.161 (CFTC) | margin for non-cleared swaps of non-bank swap dealers | `us-cfr-17-23-margin` |
| P1 | 17 CFR 240.18a-1, 240.18a-3 (SEC) | capital and margin of security-based swap dealers: single-name equity and credit swaps | `us-cfr-240-18a-1`, `-18a-3` |
| P2 | 12 CFR 217.2 (definitions), 217.10, 217.32 | definitions, minimum ratios, general risk weights | |
| P2 | 2026 re-proposal (expanded risk-based approach: FRTB-style market risk, SA-CCR changes, CVA) | proposal, Federal Register | `us-fr-2026-erba` |
| guidance | SR 26-2 (already in), SR 11-7 (kept for history) | | |

### 5.4 International, beyond the Basel Framework

| P | Text | Why |
|---|---|---|
| P1 | BCBS/IOSCO margin requirements for non-centrally cleared derivatives (d475) | the framework the three margin rules transpose; ISDA SIMM is calibrated against it |
| P2 | BCBS 239 (d239) | data aggregation: the only text for `reg-data-aggregation` |

Not collected: ISDA SIMM methodology and ISDA CDM (licence: ISDA members), national
transpositions outside the three jurisdictions.

### 5.5 Harvest (step 3, as built)

`kbase harvest-regulation --catalog configs/harvest/regulation-wave1.yaml` reads a
catalogue (source, selector, manifest metadata per document), fetches politely (3 s
between requests, generic user agent), keeps the raw source under
`$AGX_PATHS_DOCUMENTS_DIR/regulation/<jurisdiction>/raw/`, writes Markdown under `md/`
and one manifest per jurisdiction (`documents/manifest-regulation-<jurisdiction>.yaml`).
A consolidated EU text shared by several entries is fetched once.

- **eCFR**: the latest issue of each title (`titles.json`) unless the catalogue pins
  `ecfr_date`; paragraph paths read from the CFR markers, the `(i)` letter/roman
  ambiguity resolved by the expected next label.
- **EU**: the EU SPARQL endpoint lists consolidated versions. On 2026-11-13 the
  2027-01-01 consolidation of the CRR existed, but Cellar answered HTTP 500 for all its
  formats; market risk is taken from the consolidation in force (2026-06-26), which
  already holds Articles 325c–325bp, with titles that say the FRTB applies from
  2027-01-01. Switch the catalogue once Cellar serves it.
- **EU formulas** are JPEG images: saved under `img/`, placeholder `[formula: <file>]`,
  then `kbase regulation-formulas` runs MinerU once over the pending images (GPU, night
  batch), writes a LaTeX sidecar per image and puts `$…$` in place. A new harvest
  re-applies the sidecars without MinerU (`--apply-only`).
- **PRA** formulas are LaTeX in the page (`\[…\]`) and become `$$` equation blocks;
  some parts (CCR) use JPEG images (`-/media/<hash>.ashx`), downloaded under `img/`
  and read by `kbase regulation-formulas` like the EU ones.
- **eCFR** formulas that are Federal Register graphics (`/graphics/er24ja20.025.gif`)
  take the same route.
- Deferred from wave 1: UK EMIR margin RTS (legislation.gov.uk, another format), the
  BCBS/IOSCO margin framework (PDF, through the guidance manifest).

## 6. Topics

Existing `reg-*` topics are reused. Added: `reg-margin-requirements` (already used by
MGN), `reg-prudent-valuation`, `reg-definitions`, `reg-trading-book-boundary`.

## 7. Evaluation

`benchmarks/retrieval/queries-regulation.yaml` gains a `jurisdictions` field and per
jurisdiction:

- **exact-id**: `CRR Article 274(2)`, `12 CFR 217.132(c)(5)`, PRA `Article 325c`.
- **jurisdiction-specific**: questions whose answer differs by jurisdiction (SA-CCR alpha
  and the US CEM option, FRTB date, margin thresholds in EUR / USD / GBP), with the
  jurisdiction filter set; the expected document must be from that jurisdiction.
- **cross-jurisdiction trap**: the same question without a filter; scored on whether the
  top result's jurisdiction is reported, and checked by hand at first.

Gates: quant sets unchanged; Basel-only queries unchanged with `jurisdictions=["intl"]`.

## 8. Delivery order

1. Migration 0009, `jurisdiction` + new `doc_type`s, manifests, filter, citations,
   `list_topics`, `list_documents`, "not expired" default, CLI and eval. Backfill.
2. Paragraph ids and lexical normalisation for EU/UK articles and CFR paragraphs.
3. Harvesters: `harvest-eu` (Cellar), `harvest-pra` (Rulebook, dated), `harvest-ecfr`
   (versioner API). Each writes Markdown with one heading per paragraph and a manifest,
   like `harvest-basel`.
4. P1 wave for the three jurisdictions + d475; queries; night batch ingestion.
5. P2 wave, US re-proposal and UK CP9/26 as `proposal`.

WP20 step 6 (CRR3/EBA wave) is absorbed into steps 3–5.

## 9. Open questions

- The US re-proposal is long (hundreds of pages); keep only the market risk, CCR and CVA
  sections.
- When the US final rule is published, ingest it and set `valid_until` on the 2013
  sections it replaces.
- EU FRTB RTS list: established from the EBA page at harvest time and recorded here.
