"""Loads chunks (+ their document metadata) for a set of chunk ids in one query —
no N+1 (WP05 §10)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from kbase.schemas import Chunk, DocumentMeta, Equation


def load_candidates(
    session: Session, chunk_ids: list[str]
) -> dict[str, tuple[Chunk, DocumentMeta]]:
    if not chunk_ids:
        return {}
    rows = session.execute(
        text(
            "SELECT c.id, c.document_version_id, c.section_id, c.ordinal, c.kind, "
            " c.content, c.n_tokens, c.page_start, c.page_end, c.has_equations, "
            " c.valid_from, c.valid_until, c.sha256, "
            " eq.latex, eq.equation_number, eq.symbols, eq.context_before, eq.context_after, "
            " tb.caption, tb.content_md, "
            " d.doc_key, d.title, d.authors, d.year, d.doc_type, d.source_url, d.license, "
            " d.topic, d.asset_class "
            "FROM kb.chunks c "
            "JOIN kb.document_versions dv ON dv.id = c.document_version_id "
            "JOIN kb.documents d ON d.id = dv.document_id "
            "LEFT JOIN kb.equations eq ON eq.chunk_id = c.id "
            "LEFT JOIN kb.tables tb ON tb.chunk_id = c.id "
            "WHERE c.id = ANY(:chunk_ids)"
        ),
        {"chunk_ids": [str(cid) for cid in chunk_ids]},
    ).all()

    result: dict[str, tuple[Chunk, DocumentMeta]] = {}
    for row in rows:
        equation = (
            Equation(
                latex=row.latex,
                equation_number=row.equation_number,
                page=row.page_start,
                symbols=list(row.symbols) if row.symbols else [],
            )
            if row.latex is not None
            else None
        )
        chunk = Chunk(
            chunk_id=str(row.id),
            document_version_id=str(row.document_version_id),
            section_id=str(row.section_id) if row.section_id else None,
            ordinal=row.ordinal,
            kind=row.kind,
            content=row.content,
            n_tokens=row.n_tokens,
            page_start=row.page_start,
            page_end=row.page_end,
            has_equations=row.has_equations,
            valid_from=row.valid_from,
            valid_until=row.valid_until,
            sha256=row.sha256,
            equation=equation,
            table_caption=row.caption,
            table_content_md=row.content_md,
            equation_context_before=row.context_before,
            equation_context_after=row.context_after,
        )
        meta = DocumentMeta(
            doc_key=row.doc_key,
            title=row.title,
            authors=list(row.authors) if row.authors else [],
            year=row.year,
            doc_type=row.doc_type,
            source_url=row.source_url,
            license=row.license,
            topic=row.topic,
            asset_class=row.asset_class,
        )
        result[str(row.id)] = (chunk, meta)
    return result
