"""Writes one row per `HybridRetriever.retrieve()` call to `kb.retrieval_logs`
(WP05 §8) — feeds WP09 evaluation and general tracing."""

from __future__ import annotations

from corelib.serialization import to_json
from corelib.time import utc_now
from sqlalchemy import text
from sqlalchemy.orm import Session

from kbase.retrieval.query import RetrievalResult


def record(session: Session, result: RetrievalResult) -> None:
    session.execute(
        text(
            "INSERT INTO kb.retrieval_logs "
            "(id, ts, query_text, filters, strategy, k, latency_ms, "
            " result_chunk_ids, scores, correlation_id) "
            "VALUES (:id, :ts, :query_text, CAST(:filters AS jsonb), :strategy, :k, "
            " :latency_ms, CAST(:result_chunk_ids AS uuid[]), CAST(:scores AS jsonb), "
            " :correlation_id)"
        ),
        {
            "id": result.correlation_id,
            "ts": utc_now(),
            "query_text": result.query.text,
            "filters": to_json(result.query.filters.model_dump(mode="json")),
            "strategy": result.strategy_used,
            "k": result.query.k,
            "latency_ms": result.latency_ms,
            "result_chunk_ids": [c.chunk.chunk_id for c in result.chunks],
            "scores": to_json({c.chunk.chunk_id: c.scores for c in result.chunks}),
            "correlation_id": result.correlation_id,
        },
    )
