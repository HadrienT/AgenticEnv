"""Domain schemas for kbase (blueprint/03-INTERFACES.md §3.1)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from corelib.errors import ErrorDTO
from pydantic import BaseModel, Field

DocType = Literal["research_paper", "book", "documentation", "standard", "notes"]
ChunkKind = Literal["text", "equation", "table", "caption"]


class DocumentMeta(BaseModel):
    doc_key: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doc_type: DocType
    source_url: str | None = None
    license: str | None = None
    topic: str | None = None
    asset_class: str | None = None


class Section(BaseModel):
    section_id: str
    parent_id: str | None
    level: int
    ordinal: int
    title: str
    page_start: int | None = None
    page_end: int | None = None
    path: str


class Equation(BaseModel):
    latex: str
    equation_number: str | None = None
    page: int | None = None
    symbols: list[str] = Field(default_factory=list)


class ContentBlock(BaseModel):
    """Ordered unit produced by a `Parser`; the atom `Chunker` groups or never splits."""

    kind: ChunkKind
    text: str
    section_id: str | None
    page_start: int | None = None
    page_end: int | None = None
    equation: Equation | None = None  # set only when kind == "equation"
    context_before: str | None = None  # equation-only, see WP04 §5
    context_after: str | None = None  # equation-only, see WP04 §5
    table_caption: str | None = None  # set only when kind == "table"
    table_content_md: str | None = None  # set only when kind == "table"


class ParsedDocument(BaseModel):
    meta: DocumentMeta
    version: str
    sha256: str
    page_count: int | None
    sections: list[Section]
    blocks: list[ContentBlock]
    parser_name: str
    parser_version: str


class Chunk(BaseModel):
    chunk_id: str
    document_version_id: str
    section_id: str | None
    ordinal: int
    kind: ChunkKind
    content: str
    n_tokens: int
    page_start: int | None
    page_end: int | None
    has_equations: bool
    valid_from: date | None
    valid_until: date | None
    sha256: str
    equation: Equation | None = None  # populated only when kind == "equation"
    table_caption: str | None = None  # populated only when kind == "table"
    table_content_md: str | None = None  # populated only when kind == "table"
    equation_context_before: str | None = None
    equation_context_after: str | None = None


class Citation(BaseModel):
    document: str
    authors: list[str]
    year: int | None
    section: str | None
    page: int | None
    equation_number: str | None
    source_url: str | None
    sha256: str
    ingested_at: datetime


class RetrievedChunk(BaseModel):
    chunk: Chunk
    citation: Citation
    scores: dict[str, float] = Field(default_factory=dict)
    rank: int


class ChunkPolicy(BaseModel):
    strategy: Literal["structural"] = "structural"
    target_tokens: int
    max_tokens: int
    overlap_tokens: int
    keep_equation_with_context: bool = True
    never_split_within: list[str] = Field(default_factory=lambda: ["equation", "table"])


class SourceItem(BaseModel):
    """One resolved manifest entry: metadata + a path confined to `paths.documents_dir`."""

    meta: DocumentMeta
    resolved_path: str
    valid_from: date | None = None
    valid_until: date | None = None


class IngestionRequest(BaseModel):
    source: Literal["manifest", "path"]
    target: str
    force_reparse: bool = False
    dry_run: bool = False


class IngestionReport(BaseModel):
    run_id: str
    documents_seen: int
    documents_ingested: int
    documents_skipped: int
    chunks_written: int
    equations_written: int
    errors: list[ErrorDTO]
    duration_ms: int
    status: Literal["success", "partial", "failed"]
