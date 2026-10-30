"""`kbase reindex --model <name>`: re-embeds existing chunks without re-parsing (WP04 §9)."""

from __future__ import annotations

from corelib.errors import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from kbase.embeddings.base import Embedder
from kbase.ingestion.writer import format_vector

_BATCH_SIZE = 200


def reindex(session: Session, *, model_name: str, embedder: Embedder, replace: bool = False) -> int:
    """Re-embeds every chunk with `embedder`; `model_name` must match the configured model.
    Commits batch by batch, so an interrupted run resumes where it stopped: chunks the
    model already covers are skipped. `replace` then drops the other models' vectors:
    the HNSW index holds all of them, and filtering by model after the search would
    otherwise cost recall."""
    if model_name != embedder.model_name:
        raise ValidationError(
            f"unknown embedding model: {model_name!r}",
            details={"requested": model_name, "available": embedder.model_name},
        )

    reindexed = 0
    last_id: str | None = None
    while True:
        rows = session.execute(
            text(
                "SELECT c.id, c.content FROM kb.chunks c "
                "WHERE (CAST(:last_id AS text) IS NULL OR c.id::text > :last_id) "
                "AND NOT EXISTS (SELECT 1 FROM kb.chunk_embeddings e "
                "WHERE e.chunk_id = c.id AND e.model_name = :model_name "
                "AND e.model_version = :model_version) "
                "ORDER BY c.id::text LIMIT :batch_size"
            ),
            {
                "last_id": last_id,
                "batch_size": _BATCH_SIZE,
                "model_name": embedder.model_name,
                "model_version": embedder.model_version,
            },
        ).all()
        if not rows:
            break
        chunk_ids = [str(r[0]) for r in rows]
        contents = [r[1] for r in rows]
        embeddings = embedder.embed_documents(contents)
        for chunk_id, embedding in zip(chunk_ids, embeddings, strict=True):
            session.execute(
                text(
                    "INSERT INTO kb.chunk_embeddings "
                    "(chunk_id, model_name, model_version, dim, embedding) "
                    "VALUES (:chunk_id, :model_name, :model_version, :dim, "
                    "CAST(:embedding AS vector)) "
                    "ON CONFLICT (chunk_id, model_name, model_version) "
                    "DO UPDATE SET dim = EXCLUDED.dim, embedding = EXCLUDED.embedding, "
                    "created_at = now()"
                ),
                {
                    "chunk_id": chunk_id,
                    "model_name": embedder.model_name,
                    "model_version": embedder.model_version,
                    "dim": embedder.dim,
                    "embedding": format_vector(embedding),
                },
            )
        reindexed += len(rows)
        last_id = chunk_ids[-1]
        session.commit()

    if replace:
        session.execute(
            text(
                "DELETE FROM kb.chunk_embeddings "
                "WHERE NOT (model_name = :model_name AND model_version = :model_version)"
            ),
            {"model_name": embedder.model_name, "model_version": embedder.model_version},
        )
    return reindexed
