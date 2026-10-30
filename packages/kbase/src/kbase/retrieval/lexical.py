"""Full-text search over `kb.chunks.search_tsv` (GIN index, `ts_rank`)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from kbase.retrieval.fusion import RankedHit

_WORD_RE = re.compile(r"[^\W\d_]{3,}", re.UNICODE)
_STOP_WORDS_TEXT = """
the and for with that this from are was were has have how why what when does into than
then them they their its not but can may will would about over under which
les des une pour avec dans sur par que qui est sont aux ces cette comme plus entre leur
leurs mais donc
"""
_STOP_WORDS = frozenset(_STOP_WORDS_TEXT.split())


def search(
    session: Session,
    *,
    query_text: str,
    fts_config: str,
    predicate_sql: str,
    predicate_params: dict[str, Any],
    candidates_n: int,
    any_term: bool = False,
) -> list[RankedHit]:
    """Top-`candidates_n` chunks by `ts_rank`, descending (higher is more relevant).
    `any_term`: `websearch_to_tsquery` needs every word, which a sentence never
    satisfies; this keeps the content words of the query and takes any of them."""
    if any_term:
        words = [w for w in _WORD_RE.findall(query_text.lower()) if w not in _STOP_WORDS]
        if not words:
            return []
        rows = session.execute(
            text(
                "WITH q AS (SELECT to_tsquery(:fts_config, unaccent(:terms)) AS query) "
                "SELECT c.id, ts_rank(c.search_tsv, q.query) AS rank "
                "FROM kb.chunks c "
                "CROSS JOIN q "
                "JOIN kb.document_versions dv ON dv.id = c.document_version_id "
                "JOIN kb.documents d ON d.id = dv.document_id "
                "WHERE c.search_tsv @@ q.query"
                + predicate_sql
                + " ORDER BY rank DESC LIMIT :candidates_n"
            ),
            {
                "fts_config": fts_config,
                "terms": " | ".join(words),
                "candidates_n": candidates_n,
                **predicate_params,
            },
        ).all()
        return [RankedHit(chunk_id=str(row[0]), score=float(row[1])) for row in rows]

    rows = session.execute(
        text(
            "SELECT c.id, ts_rank(c.search_tsv, websearch_to_tsquery(:fts_config, "
            "unaccent(:query_text))) AS rank "
            "FROM kb.chunks c "
            "JOIN kb.document_versions dv ON dv.id = c.document_version_id "
            "JOIN kb.documents d ON d.id = dv.document_id "
            "WHERE c.search_tsv @@ websearch_to_tsquery(:fts_config, unaccent(:query_text))"
            + predicate_sql
            + " ORDER BY rank DESC LIMIT :candidates_n"
        ),
        {
            "fts_config": fts_config,
            "query_text": query_text,
            "candidates_n": candidates_n,
            **predicate_params,
        },
    ).all()
    return [RankedHit(chunk_id=str(row[0]), score=float(row[1])) for row in rows]
