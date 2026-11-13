---
name: rag-citation
description: This skill should be used when the user asks about a pricing formula, model assumption, calibration method, or any quantitative-finance concept, or mentions "equation", "model", "calibration", "formula", or "price".
triggers:
- equation
- formula
- calibration
- pricing model
- kb.search
---

# RAG Citation Discipline

Never state a formula, numeric constant, or modeling assumption from memory
alone when a knowledge-base lookup can confirm it — the knowledge base is the
source of truth, not the model's training data.

## Core Instructions

1. Before writing or explaining a formula, call `kb.search` (and
   `kb.get_equation` if a specific equation ID is known) to retrieve the
   authoritative source.
2. Cite the document/section the formula or assumption comes from in your
   answer. If `kb.search` returns nothing relevant, say so explicitly instead
   of falling back to an unverified answer.
3. Never compute a numerical pricing/calibration result by mental arithmetic
   — call the relevant `cpp.*` tool (e.g. `cpp.test`, `cpp.bench`) and read
   its actual output. Recomputing a number "in your head" instead of calling
   the tool is a known failure mode for this project (see
   `blueprint/wp/WP08-openhands-integration.md` §13).
4. If two sources disagree, report the contradiction rather than silently
   picking one.
5. `kb.search` needs `collections`: `quant` for pricing and numerics,
   `regulation` for prudential rules, both when the question spans them.
   Regulatory rules differ by jurisdiction: pass `jurisdictions` (`eu`, `us`,
   `uk`, plus `intl` for Basel) and state the jurisdiction and document type of
   every rule you cite. Cite by paragraph id (`MAR21.4`, `Article 274(2)`,
   `§ 217.132(c)(1)`); `kb.list_documents` gives the doc_keys and
   `kb.list_paragraphs` lists every paragraph of a document when a review must
   cover all its requirements.
6. The knowledge base is in English: write `kb.search` queries in English,
   whatever the language of the conversation (`Bâle` → Basel, `décote` →
   haircut). The answer stays in the language of the user's question: French
   in, French out, even though sources and searches are in English.

## Common Patterns

- "What discounting convention does this repo use?" → `kb.search` first, cite
  the section, then confirm against the actual code via `code.find_symbol`.
- "Price this option" → never estimate the number yourself; run the relevant
  `cpp.*` tool and report its output verbatim.
