from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from kbase.evaluation import ReferenceQuery, _dedup, _ndcg, _score, evaluate


def test_a_document_counts_once_at_its_best_rank() -> None:
    assert _dedup(["a", "a", "b", "a"]) == ["a", "b"]


def _chunk(doc_key: str, path: str = "", content: str = "") -> Any:
    return SimpleNamespace(
        citation=SimpleNamespace(doc_key=doc_key, section_path=path),
        chunk=SimpleNamespace(content=content),
    )


def test_score_finds_the_first_expected_document() -> None:
    query = ReferenceQuery(category="c", text="t", expected=["b", "z"])

    assert _score(query, [_chunk("a"), _chunk("b"), _chunk("z")], 1.0).hit_rank == 2
    assert _score(query, [_chunk("a")], 1.0).hit_rank is None


def test_section_hit_needs_the_document_and_the_section() -> None:
    query = ReferenceQuery(
        category="c", text="t", expected=["glasserman"], expected_sections=["Box-Muller Method"]
    )
    chunks = [
        _chunk("other", path="2 Random › Box-Muller Method"),  # right section, wrong book
        _chunk("glasserman", path="2 Random › 2.1 Generators"),
        _chunk("glasserman", content="#### Box-Muller Method\n\nTwo uniforms..."),
    ]
    scored = _score(query, chunks, 1.0)
    assert scored.hit_rank == 2 and scored.section_hit_rank == 3


def test_ndcg_is_one_for_a_perfect_ranking_and_lower_when_late() -> None:
    assert _ndcg(["a", "b"], {"a", "b"}) == pytest.approx(1.0)
    assert 0.0 < _ndcg(["x", "a"], {"a"}) < 1.0


def test_evaluate_aggregates_by_category() -> None:
    class Result:
        latency_ms = 10
        chunks = [_chunk("hit")]

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
