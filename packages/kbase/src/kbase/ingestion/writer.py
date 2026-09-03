"""`writer.upsert`: one transaction per document (WP04 §3, §8). No commit here —
the caller supplies an already-open `Session` (typically inside `session_scope()`),
so a mid-write failure rolls back the whole document, never a partial one."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from datetime import date

from corelib.errors import ConfigError
from corelib.ids import new_uuid7
from corelib.time import utc_now
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from kbase.embeddings.base import Embedder
from kbase.provenance import assert_complete, build_citation
from kbase.schemas import Chunk, ParsedDocument

_VECTOR_DIM_RE = re.compile(r"vector\((\d+)\)")


class WriteReport(BaseModel):
    document_version_id: str
    chunks_written: int
    equations_written: int


def format_vector(values: Sequence[float]) -> str:
    """pgvector's documented text input format: `[v1,v2,...]`."""
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def assert_dimension_matches(session: Session, expected_dim: int) -> None:
    """Boot-time guard: `configs/kbase.yaml → embeddings.dim` must equal the DB `vector(D)`."""
    row = session.execute(
        text(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = 'kb.chunk_embeddings'::regclass AND attname = 'embedding'"
        )
    ).first()
    if row is None:
        raise ConfigError("kb.chunk_embeddings.embedding column not found", details={})
    match = _VECTOR_DIM_RE.search(row[0])
    if not match:
        raise ConfigError(
            f"could not parse vector dimension from {row[0]!r}", details={"type": row[0]}
        )
    db_dim = int(match.group(1))
    if db_dim != expected_dim:
        raise ConfigError(
            f"embeddings.dim={expected_dim} does not match kb.chunk_embeddings vector({db_dim})",
            details={"configured_dim": expected_dim, "db_dim": db_dim},
        )


def _upsert_document_id(session: Session, doc: ParsedDocument) -> uuid.UUID:
    row = session.execute(
        text("SELECT id FROM kb.documents WHERE doc_key = :doc_key"),
        {"doc_key": doc.meta.doc_key},
    ).first()
    if row is not None:
        return uuid.UUID(str(row[0]))
    document_id = new_uuid7()
    session.execute(
        text(
            "INSERT INTO kb.documents "
            "(id, doc_key, title, authors, year, doc_type, topic, asset_class, "
            " source_url, license) "
            "VALUES (:id, :doc_key, :title, :authors, :year, :doc_type, :topic, "
            " :asset_class, :source_url, :license)"
        ),
        {
            "id": document_id,
            "doc_key": doc.meta.doc_key,
            "title": doc.meta.title,
            "authors": doc.meta.authors,
            "year": doc.meta.year,
            "doc_type": doc.meta.doc_type,
            "topic": doc.meta.topic,
            "asset_class": doc.meta.asset_class,
            "source_url": doc.meta.source_url,
            "license": doc.meta.license,
        },
    )
    return document_id


def upsert(
    session: Session,
    doc: ParsedDocument,
    chunks: list[Chunk],
    embeddings: list[Sequence[float]],
    embedder: Embedder,
    run_id: uuid.UUID,
    *,
    file_path: str,
    valid_from: date | None,
    valid_until: date | None,
    require_page: bool,
    require_section: bool,
) -> WriteReport:
    """Writes one document version, its sections, chunks, embeddings, equations and tables."""
    document_id = _upsert_document_id(session, doc)

    document_version_id = new_uuid7()
    session.execute(
        text(
            "INSERT INTO kb.document_versions "
            "(id, document_id, version, file_path, sha256, page_count, ingestion_date, "
            " parser_name, parser_version, ingestion_run_id, status) "
            "VALUES (:id, :document_id, :version, :file_path, :sha256, :page_count, :now, "
            " :parser_name, :parser_version, :run_id, 'indexed')"
        ),
        {
            "id": document_version_id,
            "document_id": document_id,
            "version": doc.version,
            "file_path": file_path,
            "sha256": doc.sha256,
            "page_count": doc.page_count,
            "now": utc_now(),
            "parser_name": doc.parser_name,
            "parser_version": doc.parser_version,
            "run_id": run_id,
        },
    )

    section_db_id: dict[str, uuid.UUID] = {}
    for section in doc.sections:
        new_section_id = new_uuid7()
        session.execute(
            text(
                "INSERT INTO kb.sections "
                "(id, document_version_id, parent_id, level, ordinal, title, "
                " page_start, page_end, path) "
                "VALUES (:id, :document_version_id, :parent_id, :level, :ordinal, :title, "
                " :page_start, :page_end, :path)"
            ),
            {
                "id": new_section_id,
                "document_version_id": document_version_id,
                "parent_id": section_db_id.get(section.parent_id) if section.parent_id else None,
                "level": section.level,
                "ordinal": section.ordinal,
                "title": section.title,
                "page_start": section.page_start,
                "page_end": section.page_end,
                "path": section.path,
            },
        )
        section_db_id[section.section_id] = new_section_id

    equations_written = 0
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        citation = build_citation(chunk, doc.meta, source_url=doc.meta.source_url)
        assert_complete(citation, require_page=require_page, require_section=require_section)

        chunk_id = new_uuid7()
        session.execute(
            text(
                "INSERT INTO kb.chunks "
                "(id, document_version_id, section_id, ordinal, kind, content, n_tokens, "
                " page_start, page_end, has_equations, valid_from, valid_until, sha256) "
                "VALUES (:id, :document_version_id, :section_id, :ordinal, :kind, :content, "
                " :n_tokens, :page_start, :page_end, :has_equations, :valid_from, :valid_until, "
                " :sha256)"
            ),
            {
                "id": chunk_id,
                "document_version_id": document_version_id,
                "section_id": section_db_id.get(chunk.section_id) if chunk.section_id else None,
                "ordinal": chunk.ordinal,
                "kind": chunk.kind,
                "content": chunk.content,
                "n_tokens": chunk.n_tokens,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "has_equations": chunk.has_equations,
                "valid_from": valid_from,
                "valid_until": valid_until,
                "sha256": chunk.sha256,
            },
        )
        session.execute(
            text(
                "INSERT INTO kb.chunk_embeddings "
                "(chunk_id, model_name, model_version, dim, embedding) "
                "VALUES (:chunk_id, :model_name, :model_version, :dim, CAST(:embedding AS vector))"
            ),
            {
                "chunk_id": chunk_id,
                "model_name": embedder.model_name,
                "model_version": embedder.model_version,
                "dim": embedder.dim,
                "embedding": format_vector(embedding),
            },
        )

        if chunk.kind == "equation" and chunk.equation is not None:
            session.execute(
                text(
                    "INSERT INTO kb.equations "
                    "(id, chunk_id, document_version_id, latex, equation_number, page, "
                    " symbols, context_before, context_after) "
                    "VALUES (:id, :chunk_id, :document_version_id, :latex, :equation_number, "
                    " :page, :symbols, :context_before, :context_after)"
                ),
                {
                    "id": new_uuid7(),
                    "chunk_id": chunk_id,
                    "document_version_id": document_version_id,
                    "latex": chunk.equation.latex,
                    "equation_number": chunk.equation.equation_number,
                    "page": chunk.equation.page,
                    "symbols": chunk.equation.symbols,
                    "context_before": chunk.equation_context_before,
                    "context_after": chunk.equation_context_after,
                },
            )
            equations_written += 1
        elif chunk.kind == "table":
            session.execute(
                text(
                    "INSERT INTO kb.tables (id, chunk_id, caption, content_md, page) "
                    "VALUES (:id, :chunk_id, :caption, :content_md, :page)"
                ),
                {
                    "id": new_uuid7(),
                    "chunk_id": chunk_id,
                    "caption": chunk.table_caption,
                    "content_md": chunk.table_content_md,
                    "page": chunk.page_start,
                },
            )

    return WriteReport(
        document_version_id=str(document_version_id),
        chunks_written=len(chunks),
        equations_written=equations_written,
    )
