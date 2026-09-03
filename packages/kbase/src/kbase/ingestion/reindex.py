"""`kbase reindex --model <name>`: re-embeds existing chunks without re-parsing (WP04 §9)."""

from __future__ import annotations

from corelib.errors import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from kbase.embeddings.base import Embedder
from kbase.ingestion.writer import format_vector

_BATCH_SIZE = 200


def reindex(session: Session, *, model_name: str, embedder: Embedder) -> int:
    """Re-embeds every chunk with `embedder`; only one local model exists today (WP04 §9),
    so `model_name` must match `embedder.model_name` — a real model registry is future work."""
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
                "SELECT id, content FROM kb.chunks "
                "WHERE (:last_id IS NULL OR id::text > :last_id) "
                "ORDER BY id::text LIMIT :batch_size"
            ),
            {"last_id": last_id, "batch_size": _BATCH_SIZE},
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

    return reindexed
