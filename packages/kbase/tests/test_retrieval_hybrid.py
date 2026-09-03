from __future__ import annotations

from collections.abc import Sequence

import pytest
from corelib.db import apply_migrations, session_scope
from corelib.errors import DependencyError
from kbase.embeddings.base import Embedder
from kbase.embeddings.hashing import HashingEmbedder
from kbase.retrieval.hybrid import HybridRetriever
from kbase.retrieval.query import RetrievalFilters, RetrievalQuery
from kbase.retrieval.rerank import LexicalOverlapReranker, Reranker
from kbase.schemas import RetrievedChunk
from sqlalchemy import text

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _migrated() -> None:
    apply_migrations()


def _retriever(
    *, reranker: Reranker | None = None, embedder: Embedder | None = None
) -> HybridRetriever:
    return HybridRetriever(
        embedder=embedder if embedder is not None else HashingEmbedder(dim=1024),
        reranker=reranker if reranker is not None else LexicalOverlapReranker(),
        candidates_vector=50,
        candidates_lexical=50,
        rrf_k=60,
        fts_config="simple",
        min_score=0.0,
        rerank_top_k=8,
        require_page=False,
        require_section=True,
    )


class _BrokenEmbedder:
    model_name = "broken"
    model_version = "1"
    dim = 1024

    def embed_documents(self, texts: Sequence[str]) -> list[Sequence[float]]:
        raise RuntimeError("embedder down")

    def embed_query(self, text: str) -> Sequence[float]:
        raise RuntimeError("embedder down")


class _BrokenReranker:
    model_name = "broken-reranker"

    def rerank(
        self, query: str, candidates: Sequence[RetrievedChunk], *, top_k: int
    ) -> list[RetrievedChunk]:
        raise RuntimeError("reranker down")


def test_lexical_finds_the_known_relevant_chunk(golden_corpus: None) -> None:
    query_text = "volatility measures the dispersion of returns"
    query = RetrievalQuery(text=query_text, k=1, strategy="lexical", rerank=False)
    result = _retriever().retrieve(query)
    assert result.chunks
    assert "dispersion of returns" in result.chunks[0].chunk.content


def test_hybrid_finds_the_known_relevant_chunk(golden_corpus: None) -> None:
    query_text = "volatility measures the dispersion of returns"
    query = RetrievalQuery(text=query_text, k=1, strategy="hybrid", rerank=False)
    result = _retriever().retrieve(query)
    assert result.chunks
    assert "dispersion of returns" in result.chunks[0].chunk.content


def test_result_citations_are_always_complete(golden_corpus: None) -> None:
    query = RetrievalQuery(text="volatility", k=5, strategy="hybrid")
    result = _retriever().retrieve(query)
    assert result.chunks
    for chunk in result.chunks:
        assert chunk.citation.document
        assert chunk.citation.sha256
        assert chunk.citation.section  # require_section=True in this fixture


def test_contradiction_warning_when_topk_spans_documents(golden_corpus: None) -> None:
    query = RetrievalQuery(text="volatility", k=4, strategy="hybrid", rerank=False)
    result = _retriever().retrieve(query)
    documents = {c.citation.document for c in result.chunks}
    if len(documents) > 1:
        assert any("divergent" in w for w in result.warnings)


def test_retrieval_log_row_is_written(golden_corpus: None) -> None:
    query = RetrievalQuery(text="volatility", k=3, strategy="hybrid")
    result = _retriever().retrieve(query)

    with session_scope() as session:
        row = session.execute(
            text("SELECT query_text, strategy, k FROM kb.retrieval_logs WHERE id = :id"),
            {"id": result.correlation_id},
        ).first()
    assert row is not None
    assert row.query_text == "volatility"
    assert row.strategy == "hybrid"
    assert row.k == 3


def test_embedder_unavailable_raises_dependency_error(golden_corpus: None) -> None:
    retriever = _retriever(embedder=_BrokenEmbedder())
    query = RetrievalQuery(text="volatility", k=3, strategy="hybrid")
    with pytest.raises(DependencyError):
        retriever.retrieve(query)


def test_lexical_only_strategy_does_not_need_the_embedder(golden_corpus: None) -> None:
    retriever = _retriever(embedder=_BrokenEmbedder())
    query = RetrievalQuery(text="volatility", k=3, strategy="lexical")
    result = retriever.retrieve(query)
    assert result.chunks


def test_reranker_unavailable_degrades_with_warning_not_exception(golden_corpus: None) -> None:
    retriever = _retriever(reranker=_BrokenReranker())
    query = RetrievalQuery(text="volatility", k=3, strategy="hybrid", rerank=True)
    result = retriever.retrieve(query)
    assert result.chunks
    assert any("reranker unavailable" in w for w in result.warnings)


def test_sql_injection_filter_is_safe_and_returns_no_rows(golden_corpus: None) -> None:
    payload = "notes'; DROP TABLE kb.chunks; --"
    query = RetrievalQuery(
        text="volatility", k=3, strategy="hybrid", filters=RetrievalFilters(doc_types=[payload])
    )
    result = _retriever().retrieve(query)
    assert result.chunks == []

    with session_scope() as session:
        count = session.execute(text("SELECT count(*) FROM kb.chunks")).scalar_one()
    assert count > 0  # table still exists and is populated: no injection occurred
