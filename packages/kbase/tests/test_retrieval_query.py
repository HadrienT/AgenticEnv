from __future__ import annotations

from datetime import UTC, datetime

from kbase.retrieval.query import RetrievalFilters, RetrievalQuery, RetrievalResult
from kbase.schemas import Chunk, Citation, RetrievedChunk


def _retrieved_chunk() -> RetrievedChunk:
    chunk = Chunk(
        chunk_id="c1",
        document_version_id="dv1",
        section_id=None,
        ordinal=0,
        kind="text",
        content="hello world",
        n_tokens=2,
        page_start=1,
        page_end=1,
        has_equations=False,
        valid_from=None,
        valid_until=None,
        sha256="deadbeef",
    )
    citation = Citation(
        document="Some Doc",
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
    return RetrievedChunk(chunk=chunk, citation=citation, scores={"fused": 1.0}, rank=1)


def test_retrieval_filters_defaults_to_no_filter() -> None:
    filters = RetrievalFilters()
    assert filters.doc_types is None
    assert filters.valid_at is None


def test_retrieval_query_defaults_to_hybrid_and_rerank() -> None:
    query = RetrievalQuery(text="volatility", k=5)
    assert query.strategy == "hybrid"
    assert query.rerank is True
    assert query.filters == RetrievalFilters()


def test_retrieval_result_round_trips_json() -> None:
    query = RetrievalQuery(text="volatility", k=1)
    result = RetrievalResult(
        query=query,
        chunks=[_retrieved_chunk()],
        total_candidates=1,
        strategy_used="hybrid",
        latency_ms=12,
        correlation_id="cid-1",
        warnings=["some warning"],
    )
    restored = RetrievalResult.model_validate_json(result.model_dump_json())
    assert restored == result
