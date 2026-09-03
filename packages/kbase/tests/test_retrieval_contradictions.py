from __future__ import annotations

from datetime import UTC, datetime

from kbase.retrieval.contradictions import detect
from kbase.schemas import Chunk, Citation, RetrievedChunk


def _retrieved(chunk_id: str, document: str) -> RetrievedChunk:
    chunk = Chunk(
        chunk_id=chunk_id,
        document_version_id="dv1",
        section_id=None,
        ordinal=0,
        kind="text",
        content="content",
        n_tokens=1,
        page_start=1,
        page_end=1,
        has_equations=False,
        valid_from=None,
        valid_until=None,
        sha256="deadbeef",
    )
    citation = Citation(
        document=document,
        authors=["A"],
        year=2024,
        section=None,
        page=1,
        equation_number=None,
        source_url=None,
        sha256="deadbeef",
        doc_key="k",
        ingested_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    return RetrievedChunk(chunk=chunk, citation=citation, scores={}, rank=1)


def test_no_warning_when_all_chunks_from_the_same_document() -> None:
    chunks = [_retrieved("a", "Doc A"), _retrieved("b", "Doc A")]
    assert detect(chunks) == []


def test_no_warning_when_no_chunks() -> None:
    assert detect([]) == []


def test_warning_when_top_k_spans_distinct_documents() -> None:
    chunks = [_retrieved("a", "Doc A"), _retrieved("b", "Doc B")]
    warnings = detect(chunks)
    assert len(warnings) == 1
    assert "Doc A" in warnings[0]
    assert "Doc B" in warnings[0]
