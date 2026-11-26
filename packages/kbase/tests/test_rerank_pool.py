from __future__ import annotations

from typing import Any, cast

from kbase.retrieval.filters import RetrievalFilters
from kbase.retrieval.hybrid import HybridRetriever
from kbase.retrieval.query import RetrievalQuery


def _retriever(pools: dict[str, int]) -> HybridRetriever:
    return HybridRetriever(
        embedder=cast(Any, None), reranker=None, candidates_vector=100,
        candidates_lexical=100, rrf_k=60, fts_config="simple", min_score=0.0,
        rerank_top_k=100, require_page=False, require_section=False,
        rerank_pool_by_collection=pools,
    )  # fmt: skip


def _query(collections: list[str] | None) -> RetrievalQuery:
    return RetrievalQuery(
        text="q", k=8, filters=RetrievalFilters(collections=cast(Any, collections))
    )


def test_a_regulation_only_search_reranks_its_smaller_pool() -> None:
    retriever = _retriever({"regulation": 50})
    assert retriever.rerank_pool(_query(["regulation"])) == 50


def test_any_collection_without_its_own_pool_keeps_the_default() -> None:
    retriever = _retriever({"regulation": 50})
    assert retriever.rerank_pool(_query(["regulation", "quant"])) == 100
    assert retriever.rerank_pool(_query(["quant"])) == 100
    assert retriever.rerank_pool(_query(None)) == 100


def test_several_collections_with_pools_take_the_largest() -> None:
    retriever = _retriever({"regulation": 50, "ir": 80})
    assert retriever.rerank_pool(_query(["regulation", "ir"])) == 80
