"""Full-text search over `kb.chunks.search_tsv` (GIN index, `ts_rank`)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from kbase.retrieval.fusion import RankedHit


def search(
    session: Session,
    *,
    query_text: str,
    fts_config: str,
    predicate_sql: str,
    predicate_params: dict[str, Any],
    candidates_n: int,
) -> list[RankedHit]:
    """Top-`candidates_n` chunks by `ts_rank`, descending (higher is more relevant)."""
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
