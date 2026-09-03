"""ANN vector search over `kb.chunk_embeddings` (pgvector HNSW, cosine distance)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from kbase.ingestion.writer import format_vector
from kbase.retrieval.fusion import RankedHit


def search(
    session: Session,
    *,
    embedding: Sequence[float],
    model_name: str,
    model_version: str,
    predicate_sql: str,
    predicate_params: dict[str, Any],
    candidates_n: int,
) -> list[RankedHit]:
    """Top-`candidates_n` chunks by cosine distance (ascending: smaller is closer)."""
    rows = session.execute(
        text(
            "SELECT c.id, ce.embedding <=> CAST(:embedding AS vector) AS distance "
            "FROM kb.chunks c "
            "JOIN kb.chunk_embeddings ce ON ce.chunk_id = c.id "
            "JOIN kb.document_versions dv ON dv.id = c.document_version_id "
            "JOIN kb.documents d ON d.id = dv.document_id "
            "WHERE ce.model_name = :model_name AND ce.model_version = :model_version"
            + predicate_sql
            + " ORDER BY distance ASC LIMIT :candidates_n"
        ),
        {
            "embedding": format_vector(embedding),
            "model_name": model_name,
            "model_version": model_version,
            "candidates_n": candidates_n,
            **predicate_params,
        },
    ).all()
    return [RankedHit(chunk_id=str(row[0]), score=float(row[1])) for row in rows]
