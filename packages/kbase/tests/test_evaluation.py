from __future__ import annotations

from typing import Any

import pytest
from kbase.evaluation import ReferenceQuery, _dedup, _ndcg, _score, evaluate


def test_a_document_counts_once_at_its_best_rank() -> None:
    assert _dedup(["a", "a", "b", "a"]) == ["a", "b"]


def test_score_finds_the_first_expected_document() -> None:
    query = ReferenceQuery(category="c", text="t", expected=["b", "z"])

    assert _score(query, ["a", "b", "z"], 1.0).hit_rank == 2
    assert _score(query, ["a"], 1.0).hit_rank is None


def test_ndcg_is_one_for_a_perfect_ranking_and_lower_when_late() -> None:
    assert _ndcg(["a", "b"], {"a", "b"}) == pytest.approx(1.0)
    assert 0.0 < _ndcg(["x", "a"], {"a"}) < 1.0


def test_evaluate_aggregates_by_category() -> None:
    class Citation:
        def __init__(self, doc_key: str) -> None:
            self.doc_key = doc_key

    class Chunk:
        def __init__(self, document: str) -> None:
            self.citation = Citation(document)

    class Result:
        latency_ms = 10
        chunks = [Chunk("hit")]

    class Retriever:
        def retrieve(self, _query: Any) -> Result:
            return Result()

    queries = [
        ReferenceQuery(category="a", text="1", expected=["hit"]),
        ReferenceQuery(category="b", text="2", expected=["miss"]),
    ]

    report = evaluate(Retriever(), queries, "label")  # type: ignore[arg-type]

    assert report.overall.recall_at_5 == 0.5
    assert report.by_category["a"].mrr == 1.0
    assert report.by_category["b"].mrr == 0.0
