"""`kbase stats` and `kbase verify` (WP04 §10)."""

from __future__ import annotations

from datetime import datetime

from corelib.errors import ConfigError
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from kbase.ingestion.writer import assert_dimension_matches


class StatsReport(BaseModel):
    documents: int
    chunks: int
    equations: int
    tables: int
    last_ingestion_at: datetime | None
    # Documents per collection (WP20).
    documents_by_collection: dict[str, int] = {}


def stats(session: Session) -> StatsReport:
    documents = session.execute(text("SELECT count(*) FROM kb.documents")).scalar_one()
    chunks = session.execute(text("SELECT count(*) FROM kb.chunks")).scalar_one()
    equations = session.execute(text("SELECT count(*) FROM kb.equations")).scalar_one()
    tables = session.execute(text("SELECT count(*) FROM kb.tables")).scalar_one()
    last_ingestion_at = session.execute(
        text("SELECT max(finished_at) FROM kb.ingestion_runs WHERE status <> 'running'")
    ).scalar_one()
    by_collection = session.execute(
        text("SELECT collection, count(*) FROM kb.documents GROUP BY collection ORDER BY 1")
    ).all()
    return StatsReport(
        documents_by_collection={row[0]: row[1] for row in by_collection},
        documents=documents,
        chunks=chunks,
        equations=equations,
        tables=tables,
        last_ingestion_at=last_ingestion_at,
    )


class VerificationReport(BaseModel):
    dimension_ok: bool
    chunks_missing_embeddings: int
    chunks_missing_required_section: int
    equations_orphaned: int

    @property
    def ok(self) -> bool:
        return (
            self.dimension_ok
            and self.chunks_missing_embeddings == 0
            and self.chunks_missing_required_section == 0
            and self.equations_orphaned == 0
        )


def verify(
    session: Session,
    *,
    expected_dim: int,
    model_name: str,
    model_version: str,
    require_section: bool,
) -> VerificationReport:
    dimension_ok = True
    try:
        assert_dimension_matches(session, expected_dim)
    except ConfigError:
        dimension_ok = False

    chunks_missing_embeddings = session.execute(
        text(
            "SELECT count(*) FROM kb.chunks c WHERE NOT EXISTS ("
            "SELECT 1 FROM kb.chunk_embeddings e WHERE e.chunk_id = c.id "
            "AND e.model_name = :model_name AND e.model_version = :model_version)"
        ),
        {"model_name": model_name, "model_version": model_version},
    ).scalar_one()

    chunks_missing_required_section = (
        session.execute(
            text("SELECT count(*) FROM kb.chunks WHERE section_id IS NULL")
        ).scalar_one()
        if require_section
        else 0
    )

    # An equation belongs to its own `equation` chunk (structural chunking) or sits in
    # the text of the chunk it points at (section chunking, WP19).
    equations_orphaned = session.execute(
        text(
            "SELECT count(*) FROM kb.equations eq "
            "JOIN kb.chunks c ON c.id = eq.chunk_id "
            "WHERE c.kind <> 'equation' AND strpos(c.content, eq.latex) = 0"
        )
    ).scalar_one()

    return VerificationReport(
        dimension_ok=dimension_ok,
        chunks_missing_embeddings=chunks_missing_embeddings,
        chunks_missing_required_section=chunks_missing_required_section,
        equations_orphaned=equations_orphaned,
    )


def delete_documents(session: Session, doc_keys: list[str]) -> list[str]:
    """Removes documents and everything derived from them (cascade); returns the keys
    that existed."""
    rows = session.execute(
        text("DELETE FROM kb.documents WHERE doc_key = ANY(:keys) RETURNING doc_key"),
        {"keys": doc_keys},
    ).all()
    return sorted(str(r[0]) for r in rows)
