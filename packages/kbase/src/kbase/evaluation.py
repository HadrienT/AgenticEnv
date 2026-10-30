"""`kbase eval`: measures search on the reference queries (WP13 §1). A document counts
once, at its best rank: the question is whether the agent is led to the right source."""

from __future__ import annotations

import math
import statistics
from pathlib import Path

import yaml
from pydantic import BaseModel

from kbase.retrieval.hybrid import HybridRetriever
from kbase.retrieval.query import RetrievalFilters, RetrievalQuery

_K_RECALL = (5, 10)
_K_NDCG = 10


class ReferenceQuery(BaseModel):
    category: str
    text: str
    expected: list[str]


class Metrics(BaseModel):
    queries: int
    recall_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_10: float
    latency_p50_ms: float
    latency_p95_ms: float


class EvalReport(BaseModel):
    label: str
    overall: Metrics
    by_category: dict[str, Metrics]


class _Scored(BaseModel):
    category: str
    hit_rank: int | None
    ndcg: float
    latency_ms: float


def load_queries(path: Path) -> list[ReferenceQuery]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [ReferenceQuery.model_validate(entry) for entry in raw["queries"]]


def _dedup(doc_keys: list[str]) -> list[str]:
    return list(dict.fromkeys(doc_keys))


def _ndcg(ranked: list[str], expected: set[str]) -> float:
    gains = [1.0 / math.log2(i + 2) for i, doc in enumerate(ranked[:_K_NDCG]) if doc in expected]
    ideal = [1.0 / math.log2(i + 2) for i in range(min(len(expected), _K_NDCG))]
    return sum(gains) / sum(ideal) if ideal else 0.0


def _score(query: ReferenceQuery, ranked: list[str], latency_ms: float) -> _Scored:
    expected = set(query.expected)
    hit_rank = next((i for i, doc in enumerate(ranked, start=1) if doc in expected), None)
    return _Scored(
        category=query.category,
        hit_rank=hit_rank,
        ndcg=_ndcg(ranked, expected),
        latency_ms=latency_ms,
    )


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def _aggregate(scored: list[_Scored]) -> Metrics:
    def recall(k: int) -> float:
        return statistics.fmean(s.hit_rank is not None and s.hit_rank <= k for s in scored)

    latencies = [s.latency_ms for s in scored]
    return Metrics(
        queries=len(scored),
        recall_at_5=recall(_K_RECALL[0]),
        recall_at_10=recall(_K_RECALL[1]),
        mrr=statistics.fmean(1.0 / s.hit_rank if s.hit_rank else 0.0 for s in scored),
        ndcg_at_10=statistics.fmean(s.ndcg for s in scored),
        latency_p50_ms=_percentile(latencies, 0.5),
        latency_p95_ms=_percentile(latencies, 0.95),
    )


def evaluate(retriever: HybridRetriever, queries: list[ReferenceQuery], label: str) -> EvalReport:
    scored: list[_Scored] = []
    for query in queries:
        result = retriever.retrieve(
            RetrievalQuery(text=query.text, k=20, filters=RetrievalFilters(), strategy="hybrid")
        )
        ranked = _dedup([chunk.citation.doc_key for chunk in result.chunks])
        scored.append(_score(query, ranked, float(result.latency_ms)))
    categories = sorted({s.category for s in scored})
    return EvalReport(
        label=label,
        overall=_aggregate(scored),
        by_category={c: _aggregate([s for s in scored if s.category == c]) for c in categories},
    )
