"""Single-item lookups backing `kb.get_document` / `kb.get_equation` / `kb.list_topics`
(blueprint/wp/WP06-kbase-mcp.md §1). Fixed queries only — no dynamic filter ever reaches
SQL here, so there is no allowlist to enforce (unlike `retrieval.filters`)."""

from __future__ import annotations

from datetime import date, datetime

from corelib.errors import NotFoundError, ValidationError
from corelib.time import utc_now
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from kbase.contextual import PATH_SEPARATOR
from kbase.regulatory import matches_prefix
from kbase.retrieval.store import load_section_paths
from kbase.schemas import Citation, DocumentMeta, Equation, Section


class DocumentDetail(BaseModel):
    meta: DocumentMeta
    document_version_id: str
    version: str
    sha256: str
    page_count: int | None
    ingestion_date: datetime
    sections: list[Section]


class EquationDetail(BaseModel):
    chunk_id: str
    equation: Equation
    context_before: str | None
    context_after: str | None
    citation: Citation


class CollectionSummary(BaseModel):
    description: str | None
    document_count: int
    topics: dict[str, int]  # topic -> document count
    doc_types: list[str]
    year_min: int | None
    year_max: int | None


class TopicsSummary(BaseModel):
    topics: list[str]
    asset_classes: list[str]
    doc_types: list[str]
    year_min: int | None
    year_max: int | None
    document_count: int
    collections: dict[str, CollectionSummary] = {}


class ParagraphEntry(BaseModel):
    paragraph_id: str
    section_path: str
    first_line: str


class ParagraphText(BaseModel):
    paragraph_ids: list[str]
    section_path: str
    content: str


class ParagraphListing(BaseModel):
    """Every regulatory paragraph of one document, in reading order (WP20 §6.3).
    `texts` holds the chunks of the paragraphs matching `prefix`, when one is given."""

    doc_key: str
    title: str
    collection: str
    valid_from: date | None
    valid_until: date | None
    paragraphs: list[ParagraphEntry]
    texts: list[ParagraphText] = []
    truncated: bool = False


def get_document(
    session: Session, *, doc_key: str | None = None, document_version_id: str | None = None
) -> DocumentDetail:
    """Metadata + section tree. Exactly one of `doc_key` (latest version) or
    `document_version_id` (a specific version) must be given."""
    if (doc_key is None) == (document_version_id is None):
        raise ValidationError(
            "exactly one of doc_key or document_version_id is required",
            details={"doc_key": doc_key, "document_version_id": document_version_id},
        )

    base_query = (
        "SELECT dv.id, dv.version, dv.sha256, dv.page_count, dv.ingestion_date, "
        " d.doc_key, d.title, d.authors, d.year, d.doc_type, d.source_url, d.license, "
        " d.topic, d.asset_class, d.collection "
        "FROM kb.document_versions dv JOIN kb.documents d ON d.id = dv.document_id "
    )
    if document_version_id is not None:
        row = session.execute(
            text(base_query + "WHERE dv.id = :id"), {"id": document_version_id}
        ).first()
    else:
        row = session.execute(
            text(base_query + "WHERE d.doc_key = :doc_key ORDER BY dv.ingestion_date DESC LIMIT 1"),
            {"doc_key": doc_key},
        ).first()

    if row is None:
        raise NotFoundError(
            "document not found",
            details={"doc_key": doc_key, "document_version_id": document_version_id},
        )

    section_rows = session.execute(
        text(
            "SELECT id, parent_id, level, ordinal, title, page_start, page_end, path "
            "FROM kb.sections WHERE document_version_id = :dv_id ORDER BY ordinal"
        ),
        {"dv_id": row.id},
    ).all()
    sections = [
        Section(
            section_id=str(r.id),
            parent_id=str(r.parent_id) if r.parent_id else None,
            level=r.level,
            ordinal=r.ordinal,
            title=r.title,
            page_start=r.page_start,
            page_end=r.page_end,
            path=r.path,
        )
        for r in section_rows
    ]

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
        collection=row.collection,
    )
    return DocumentDetail(
        meta=meta,
        document_version_id=str(row.id),
        version=row.version,
        sha256=row.sha256,
        page_count=row.page_count,
        ingestion_date=row.ingestion_date,
        sections=sections,
    )


def get_equation(
    session: Session,
    *,
    doc_key: str | None = None,
    equation_number: str | None = None,
    chunk_id: str | None = None,
) -> EquationDetail:
    """Equation + context + citation, identified by `chunk_id` alone, or by
    `doc_key` + `equation_number` together."""
    base_query = (
        "SELECT eq.chunk_id, eq.latex, eq.equation_number, eq.page, eq.symbols, "
        " eq.context_before, eq.context_after, c.sha256, c.section_id, "
        " d.doc_key, d.title, d.authors, d.year, d.source_url "
        "FROM kb.equations eq "
        "JOIN kb.chunks c ON c.id = eq.chunk_id "
        "JOIN kb.document_versions dv ON dv.id = eq.document_version_id "
        "JOIN kb.documents d ON d.id = dv.document_id "
    )
    if chunk_id is not None:
        if doc_key is not None or equation_number is not None:
            raise ValidationError(
                "chunk_id is exclusive of doc_key/equation_number", details={"chunk_id": chunk_id}
            )
        row = session.execute(
            text(base_query + "WHERE eq.chunk_id = :chunk_id"), {"chunk_id": chunk_id}
        ).first()
    elif doc_key is not None and equation_number is not None:
        row = session.execute(
            text(
                base_query + "WHERE d.doc_key = :doc_key AND eq.equation_number = :equation_number "
                "ORDER BY dv.ingestion_date DESC LIMIT 1"
            ),
            {"doc_key": doc_key, "equation_number": equation_number},
        ).first()
    else:
        raise ValidationError(
            "either chunk_id, or both doc_key and equation_number, is required",
            details={"doc_key": doc_key, "equation_number": equation_number, "chunk_id": chunk_id},
        )

    if row is None:
        raise NotFoundError(
            "equation not found",
            details={"doc_key": doc_key, "equation_number": equation_number, "chunk_id": chunk_id},
        )

    section_title = None
    if row.section_id is not None:
        section_title = session.execute(
            text("SELECT title FROM kb.sections WHERE id = :id"), {"id": row.section_id}
        ).scalar_one_or_none()

    equation = Equation(
        latex=row.latex,
        equation_number=row.equation_number,
        page=row.page,
        symbols=list(row.symbols) if row.symbols else [],
    )
    citation = Citation(
        document=row.title,
        authors=list(row.authors) if row.authors else [],
        year=row.year,
        section=section_title,
        page=row.page,
        equation_number=row.equation_number,
        source_url=row.source_url,
        sha256=row.sha256,
        doc_key=row.doc_key,
        ingested_at=utc_now(),
    )
    return EquationDetail(
        chunk_id=str(row.chunk_id),
        equation=equation,
        context_before=row.context_before,
        context_after=row.context_after,
        citation=citation,
    )


def list_topics(session: Session, *, descriptions: dict[str, str] | None = None) -> TopicsSummary:
    """Lets the caller discover what the base contains before searching (WP06 §1),
    collection by collection (WP20 §4); `descriptions` come from the kbase config."""
    topics = (
        session.execute(
            text("SELECT DISTINCT topic FROM kb.documents WHERE topic IS NOT NULL ORDER BY topic")
        )
        .scalars()
        .all()
    )
    asset_classes = (
        session.execute(
            text(
                "SELECT DISTINCT asset_class FROM kb.documents "
                "WHERE asset_class IS NOT NULL ORDER BY asset_class"
            )
        )
        .scalars()
        .all()
    )
    doc_types = (
        session.execute(text("SELECT DISTINCT doc_type FROM kb.documents ORDER BY doc_type"))
        .scalars()
        .all()
    )
    row = session.execute(text("SELECT min(year), max(year), count(*) FROM kb.documents")).one()

    collections: dict[str, CollectionSummary] = {}
    for name, count, doc_type_list, year_min, year_max in session.execute(
        text(
            "SELECT collection, count(*), array_agg(DISTINCT doc_type ORDER BY doc_type), "
            " min(year), max(year) FROM kb.documents GROUP BY collection ORDER BY collection"
        )
    ).all():
        collections[name] = CollectionSummary(
            description=(descriptions or {}).get(name),
            document_count=count,
            topics={},
            doc_types=list(doc_type_list),
            year_min=year_min,
            year_max=year_max,
        )
    for name, topic, count in session.execute(
        text(
            "SELECT collection, topic, count(*) FROM kb.documents WHERE topic IS NOT NULL "
            "GROUP BY collection, topic ORDER BY collection, topic"
        )
    ).all():
        collections[name].topics[topic] = count
    for name, description in (descriptions or {}).items():
        collections.setdefault(
            name,
            CollectionSummary(
                description=description,
                document_count=0,
                topics={},
                doc_types=[],
                year_min=None,
                year_max=None,
            ),
        )

    return TopicsSummary(
        collections=collections,
        topics=list(topics),
        asset_classes=list(asset_classes),
        doc_types=list(doc_types),
        year_min=row[0],
        year_max=row[1],
        document_count=row[2],
    )


_MAX_PARAGRAPH_TEXTS = 40


def list_paragraphs(
    session: Session, *, doc_key: str, prefix: str | None = None
) -> ParagraphListing:
    """Every paragraph id of the latest version of `doc_key`, in reading order, with
    its section path and first line. With `prefix` (`MAR21.4`, or `MAR21` for a whole
    chapter), also the full text of the chunks holding the matching paragraphs. A
    review needs the whole list: a search only returns its top k (WP20 §6.3, §7)."""
    head = session.execute(
        text(
            "SELECT dv.id, d.title, d.collection FROM kb.document_versions dv "
            "JOIN kb.documents d ON d.id = dv.document_id WHERE d.doc_key = :doc_key "
            "ORDER BY dv.ingestion_date DESC LIMIT 1"
        ),
        {"doc_key": doc_key},
    ).first()
    if head is None:
        raise NotFoundError("document not found", details={"doc_key": doc_key})

    rows = session.execute(
        text(
            "SELECT c.ordinal, c.paragraph_ids, c.content, c.section_id, c.valid_from, "
            " c.valid_until FROM kb.chunks c WHERE c.document_version_id = :dv_id "
            "ORDER BY c.ordinal"
        ),
        {"dv_id": head.id},
    ).all()

    paths = load_section_paths(session, [str(r.section_id) for r in rows if r.section_id])

    def path_of(section_id: object) -> str:
        return PATH_SEPARATOR.join(paths.get(str(section_id), [])) if section_id else ""

    paragraphs: list[ParagraphEntry] = []
    seen: set[str] = set()
    texts: list[ParagraphText] = []
    truncated = False
    for row in rows:
        ids = list(row.paragraph_ids or [])
        for pid in ids:
            if pid in seen:
                continue
            seen.add(pid)
            paragraphs.append(
                ParagraphEntry(
                    paragraph_id=pid,
                    section_path=path_of(row.section_id),
                    first_line=_first_line_after(row.content, pid),
                )
            )
        if prefix and any(matches_prefix(pid, prefix) for pid in ids):
            if len(texts) < _MAX_PARAGRAPH_TEXTS:
                texts.append(
                    ParagraphText(
                        paragraph_ids=ids, section_path=path_of(row.section_id), content=row.content
                    )
                )
            else:
                truncated = True

    if prefix and not texts:
        raise NotFoundError(
            f"no paragraph matching {prefix!r} in {doc_key}",
            details={"doc_key": doc_key, "prefix": prefix},
        )
    return ParagraphListing(
        doc_key=doc_key,
        title=head.title,
        collection=head.collection,
        valid_from=rows[0].valid_from if rows else None,
        valid_until=rows[0].valid_until if rows else None,
        paragraphs=paragraphs,
        texts=texts,
        truncated=truncated,
    )


def _first_line_after(content: str, paragraph: str, limit: int = 160) -> str:
    """The first line of prose under the paragraph's heading in a chunk."""
    lines = content.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if line.lstrip("#").strip() == paragraph:
            start = i + 1
            break
    for line in lines[start:]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped if len(stripped) <= limit else stripped[: limit - 1] + "…"
    return ""
