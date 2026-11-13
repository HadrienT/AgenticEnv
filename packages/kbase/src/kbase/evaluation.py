"""`kbase eval`: measures search on the reference queries (WP13 §1). A document counts
once, at its best rank: the question is whether the agent is led to the right source."""

from __future__ import annotations

import math
import statistics
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel

from kbase.retrieval.hybrid import HybridRetriever
from kbase.retrieval.query import RetrievalFilters, RetrievalQuery
from kbase.schemas import Collection, Jurisdiction, RetrievedChunk

_K_RECALL = (5, 10)
_K_NDCG = 10


class ReferenceQuery(BaseModel):
    category: str
    text: str
    expected: list[str]
    # Section titles that answer the query (inside an `expected` document): scores the
    # passage, not only the document. A hit is a chunk of an expected document whose
    # section path or content carries one of these titles.
    expected_sections: list[str] = []
    # Regulatory paragraph ids that answer the query (`MAR21.4`): an exact match on the
    # chunk's `paragraph_ids`, scored like `expected_sections` (WP20 §8).
    expected_paragraphs: list[str] = []
    # Searched as the agent would: these collections, the text in force at `valid_at`.
    # A `--collection` given to `kbase eval` overrides `collections`.
    collections: list[Collection] | None = None
    valid_at: date | None = None
    # Restricts regulatory results to these jurisdictions (WP21 §7); `--jurisdiction`
    # given to `kbase eval` overrides it.
    jurisdictions: list[Jurisdiction] | None = None


class Metrics(BaseModel):
    queries: int
    recall_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_10: float
    latency_p50_ms: float
    latency_p95_ms: float
    # Over the queries that name `expected_sections`; ranks are chunk ranks.
    section_queries: int = 0
    section_recall_at_5: float | None = None
    section_recall_at_10: float | None = None
    section_mrr: float | None = None


class QueryDetail(BaseModel):
    text: str
    category: str
    hit_rank: int | None
    section_hit_rank: int | None
    top_documents: list[str]


class EvalReport(BaseModel):
    label: str
    overall: Metrics
    by_category: dict[str, Metrics]
    details: list[QueryDetail] = []


class _Scored(BaseModel):
    category: str
    hit_rank: int | None
    ndcg: float
    latency_ms: float
    section_hit_rank: int | None = None
    has_sections: bool = False


def load_queries(path: Path) -> list[ReferenceQuery]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [ReferenceQuery.model_validate(entry) for entry in raw["queries"]]


def _dedup(doc_keys: list[str]) -> list[str]:
    return list(dict.fromkeys(doc_keys))


def _ndcg(ranked: list[str], expected: set[str]) -> float:
    gains = [1.0 / math.log2(i + 2) for i, doc in enumerate(ranked[:_K_NDCG]) if doc in expected]
    ideal = [1.0 / math.log2(i + 2) for i in range(min(len(expected), _K_NDCG))]
    return sum(gains) / sum(ideal) if ideal else 0.0


def _section_hit(query: ReferenceQuery, chunk: RetrievedChunk) -> bool:
    if chunk.citation.doc_key not in query.expected:
        return False
    if query.expected_paragraphs and set(query.expected_paragraphs) & set(
        chunk.citation.paragraph_ids
    ):
        return True
    haystack = f"{chunk.citation.section_path or ''}\n{chunk.chunk.content}".lower()
    return any(title.lower() in haystack for title in query.expected_sections)


def _has_passages(query: ReferenceQuery) -> bool:
    return bool(query.expected_sections or query.expected_paragraphs)


def _score(query: ReferenceQuery, chunks: list[RetrievedChunk], latency_ms: float) -> _Scored:
    expected = set(query.expected)
    ranked = _dedup([chunk.citation.doc_key for chunk in chunks])
    hit_rank = next((i for i, doc in enumerate(ranked, start=1) if doc in expected), None)
    section_hit_rank = (
        next((i for i, c in enumerate(chunks, start=1) if _section_hit(query, c)), None)
        if _has_passages(query)
        else None
    )
    return _Scored(
        category=query.category,
        hit_rank=hit_rank,
        ndcg=_ndcg(ranked, expected),
        latency_ms=latency_ms,
        section_hit_rank=section_hit_rank,
        has_sections=_has_passages(query),
    )


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def _aggregate(scored: list[_Scored]) -> Metrics:
    def recall(k: int) -> float:
        return statistics.fmean(s.hit_rank is not None and s.hit_rank <= k for s in scored)

    latencies = [s.latency_ms for s in scored]
    with_sections = [s for s in scored if s.has_sections]

    def section_recall(k: int) -> float | None:
        if not with_sections:
            return None
        return statistics.fmean(
            s.section_hit_rank is not None and s.section_hit_rank <= k for s in with_sections
        )

    return Metrics(
        queries=len(scored),
        recall_at_5=recall(_K_RECALL[0]),
        recall_at_10=recall(_K_RECALL[1]),
        mrr=statistics.fmean(1.0 / s.hit_rank if s.hit_rank else 0.0 for s in scored),
        ndcg_at_10=statistics.fmean(s.ndcg for s in scored),
        latency_p50_ms=_percentile(latencies, 0.5),
        latency_p95_ms=_percentile(latencies, 0.95),
        section_queries=len(with_sections),
        section_recall_at_5=section_recall(_K_RECALL[0]),
        section_recall_at_10=section_recall(_K_RECALL[1]),
        section_mrr=statistics.fmean(
            1.0 / s.section_hit_rank if s.section_hit_rank else 0.0 for s in with_sections
        )
        if with_sections
        else None,
    )


def evaluate(
    retriever: HybridRetriever,
    queries: list[ReferenceQuery],
    label: str,
    *,
    details: bool = False,
    collections: list[Collection] | None = None,
    jurisdictions: list[Jurisdiction] | None = None,
) -> EvalReport:
    """`collections` and `jurisdictions` override every query's own (None: each query's,
    else no filter)."""
    scored: list[_Scored] = []
    rows: list[QueryDetail] = []
    for query in queries:
        filters = RetrievalFilters(
            collections=collections or query.collections,
            jurisdictions=jurisdictions or query.jurisdictions,
            valid_at=query.valid_at,
        )
        result = retriever.retrieve(
            RetrievalQuery(text=query.text, k=20, filters=filters, strategy="hybrid")
        )
        item = _score(query, result.chunks, float(result.latency_ms))
        scored.append(item)
        if details:
            rows.append(
                QueryDetail(
                    text=query.text,
                    category=query.category,
                    hit_rank=item.hit_rank,
                    section_hit_rank=item.section_hit_rank,
                    top_documents=_dedup([c.citation.doc_key for c in result.chunks])[:5],
                )
            )
    categories = sorted({s.category for s in scored})
    return EvalReport(
        label=label,
        overall=_aggregate(scored),
        by_category={c: _aggregate([s for s in scored if s.category == c]) for c in categories},
        details=rows,
    )
