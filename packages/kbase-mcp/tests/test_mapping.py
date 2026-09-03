from __future__ import annotations

from datetime import UTC, date, datetime

from kbase.schemas import Chunk, Citation, RetrievedChunk
from kbase_mcp.mapping import build_query, search_result_to_payload


def _retrieved(chunk_id: str, doc_key: str, rank: int) -> RetrievedChunk:
    chunk = Chunk(
        chunk_id=chunk_id,
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
        section="1",
        page=1,
        equation_number=None,
        source_url=None,
        sha256="deadbeef",
        doc_key=doc_key,
        ingested_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    return RetrievedChunk(chunk=chunk, citation=citation, scores={"fused": 1.0 / rank}, rank=rank)


def test_build_query_maps_flat_args_to_a_retrieval_query_with_allowlisted_filters() -> None:
    query = build_query(
        text="Heston calibration",
        k=8,
        strategy="hybrid",
        rerank=True,
        doc_types=["research_paper"],
        topics=["volatility"],
        asset_classes=None,
        doc_keys=None,
        year_min=2000,
        year_max=None,
        has_equations=True,
        valid_at=date(2026, 1, 1),
    )
    assert query.text == "Heston calibration"
    assert query.k == 8
    assert query.strategy == "hybrid"
    assert query.filters.doc_types == ["research_paper"]
    assert query.filters.topics == ["volatility"]
    assert query.filters.year_min == 2000
    assert query.filters.has_equations is True


def test_search_result_to_payload_shapes_results_and_meta() -> None:
    from kbase.retrieval.query import RetrievalQuery, RetrievalResult

    chunks = [_retrieved("a", "doc-a", 1), _retrieved("b", "doc-b", 2)]
    result = RetrievalResult(
        query=RetrievalQuery(text="x", k=2),
        chunks=chunks,
        total_candidates=5,
        strategy_used="hybrid",
        latency_ms=12,
        correlation_id="cid",
        warnings=["reranker unavailable"],
    )

    data, meta_extra = search_result_to_payload(result)

    assert [r["rank"] for r in data["results"]] == [1, 2]
    assert data["results"][0]["citation"]["doc_key"] == "doc-a"
    assert data["warnings"] == ["reranker unavailable"]
    assert meta_extra["strategy_used"] == "hybrid"
    assert meta_extra["total_candidates"] == 5
    assert meta_extra["provenance"] == ["doc-a", "doc-b"]
