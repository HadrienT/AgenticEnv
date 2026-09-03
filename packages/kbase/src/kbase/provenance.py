"""Chunk provenance: construction and the completeness invariant (WP04 §6, §14)."""

from __future__ import annotations

from typing import Literal

from corelib.errors import ValidationError
from corelib.time import utc_now

from kbase.schemas import Chunk, Citation, DocumentMeta


def build_citation(chunk: Chunk, meta: DocumentMeta, *, source_url: str | None = None) -> Citation:
    """Assembles a `Citation` from a written chunk and its document's metadata."""
    return Citation(
        document=meta.title,
        authors=meta.authors,
        year=meta.year,
        section=chunk.section_id,
        page=chunk.page_start,
        equation_number=chunk.equation.equation_number if chunk.equation else None,
        source_url=source_url if source_url is not None else meta.source_url,
        sha256=chunk.sha256,
        ingested_at=utc_now(),
    )


def assert_complete(citation: Citation, *, require_page: bool, require_section: bool) -> None:
    """Raises `ValidationError` if a mandatory provenance field is missing (WP04 §6)."""
    missing: list[str] = []
    if not citation.document:
        missing.append("document")
    if not citation.sha256:
        missing.append("sha256")
    if require_section and not citation.section:
        missing.append("section")
    if require_page and citation.page is None:
        missing.append("page")
    if missing:
        raise ValidationError(
            f"incomplete citation, missing field(s): {', '.join(missing)}",
            details={"missing": missing, "sha256": citation.sha256},
        )


def format_citation(citation: Citation, style: Literal["short", "full"]) -> str:
    """Renders a human-readable citation string, `short` (inline) or `full` (footnote)."""
    author = citation.authors[0] + " et al." if citation.authors else "Unknown"
    year = str(citation.year) if citation.year is not None else "n.d."
    if style == "short":
        return f"({author}, {year})"
    parts = [f"{author} ({year}). {citation.document}."]
    if citation.section:
        parts.append(f"§{citation.section}.")
    if citation.page is not None:
        parts.append(f"p. {citation.page}.")
    if citation.equation_number:
        parts.append(f"eq. {citation.equation_number}.")
    if citation.source_url:
        parts.append(citation.source_url)
    return " ".join(parts)
