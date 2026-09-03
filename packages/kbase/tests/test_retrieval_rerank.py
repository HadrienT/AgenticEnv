from __future__ import annotations

from datetime import UTC, datetime

from kbase.retrieval.rerank import LexicalOverlapReranker
from kbase.schemas import Chunk, Citation, RetrievedChunk


def _retrieved(chunk_id: str, content: str, rank: int) -> RetrievedChunk:
    chunk = Chunk(
        chunk_id=chunk_id,
        document_version_id="dv1",
        section_id=None,
        ordinal=0,
        kind="text",
        content=content,
        n_tokens=len(content.split()),
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
        ingested_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    return RetrievedChunk(chunk=chunk, citation=citation, scores={"fused": 1.0 / rank}, rank=rank)


def test_reranker_reorders_by_token_overlap_and_is_deterministic() -> None:
    reranker = LexicalOverlapReranker()
    low_overlap = _retrieved("low", "completely unrelated banana content", rank=1)
    high_overlap = _retrieved("high", "volatility model estimation for risk", rank=2)

    result = reranker.rerank("volatility model risk", [low_overlap, high_overlap], top_k=2)

    assert [c.chunk.chunk_id for c in result] == ["high", "low"]
    assert result[0].rank == 1
    assert result[1].rank == 2
    assert result[0].scores["rerank"] > result[1].scores["rerank"]

    # Determinism: re-running with the same inputs gives the same order and scores.
    again = reranker.rerank("volatility model risk", [low_overlap, high_overlap], top_k=2)
    assert [c.chunk.chunk_id for c in again] == [c.chunk.chunk_id for c in result]
    assert again[0].scores["rerank"] == result[0].scores["rerank"]


def test_reranker_respects_top_k() -> None:
    reranker = LexicalOverlapReranker()
    candidates = [_retrieved(f"c{i}", f"token{i} volatility", rank=i + 1) for i in range(5)]
    result = reranker.rerank("volatility", candidates, top_k=2)
    assert len(result) == 2


def test_reranker_preserves_upstream_scores() -> None:
    reranker = LexicalOverlapReranker()
    chunk = _retrieved("a", "volatility risk", rank=1)
    result = reranker.rerank("volatility", [chunk], top_k=1)
    assert result[0].scores["fused"] == chunk.scores["fused"]
    assert "rerank" in result[0].scores
