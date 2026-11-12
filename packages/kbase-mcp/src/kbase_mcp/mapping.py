"""JSON <-> kbase DTO mapping shared by the `kb.*` tools (blueprint tree kbase-mcp/mapping.py).
Kept separate from `tools/dispatch.py`: this module is the M2 "no business logic" boundary —
it only reshapes flat MCP args/results, it never talks to the database itself."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from corelib.errors import ValidationError
from corelib.time import utc_now
from kbase.retrieval.query import RetrievalFilters, RetrievalQuery, RetrievalResult
from kbase.schemas import Collection, RetrievedChunk


def build_query(
    *,
    text: str,
    collections: list[Collection],
    k: int,
    strategy: Literal["hybrid", "vector", "lexical"],
    rerank: bool,
    doc_types: list[str] | None,
    topics: list[str] | None,
    asset_classes: list[str] | None,
    doc_keys: list[str] | None,
    year_min: int | None,
    year_max: int | None,
    has_equations: bool | None,
    valid_at: date | None,
) -> RetrievalQuery:
    """Maps flat `kb.search` tool args to a `RetrievalQuery` (allowlisted filters, WP05 §3).
    The agent always names the collections it searches (WP20 §4); regulatory text is
    searched as in force today unless `valid_at` says otherwise (WP20 §5.3)."""
    if not collections:
        raise ValidationError(
            "collections must name at least one collection", details={"collections": []}
        )
    if valid_at is None and "regulation" in collections:
        valid_at = utc_now().date()
    filters = RetrievalFilters(
        collections=list(dict.fromkeys(collections)),
        doc_types=doc_types,
        topics=topics,
        asset_classes=asset_classes,
        doc_keys=doc_keys,
        year_min=year_min,
        year_max=year_max,
        has_equations=has_equations,
        valid_at=valid_at,
    )
    return RetrievalQuery(text=text, k=k, filters=filters, strategy=strategy, rerank=rerank)


def _chunk_to_result(chunk: RetrievedChunk) -> dict[str, Any]:
    return {
        "rank": chunk.rank,
        "content": chunk.chunk.content,
        "kind": chunk.chunk.kind,
        "citation": chunk.citation.model_dump(mode="json"),
        "scores": chunk.scores,
    }


def search_result_to_payload(result: RetrievalResult) -> tuple[dict[str, Any], dict[str, Any]]:
    """`(data, meta_extra)` for `kb.search`'s response envelope (WP06 §2)."""
    data = {
        "results": [_chunk_to_result(c) for c in result.chunks],
        "warnings": result.warnings,
    }
    provenance = sorted({c.citation.doc_key for c in result.chunks})
    meta_extra = {
        "strategy_used": result.strategy_used,
        "total_candidates": result.total_candidates,
        "provenance": provenance,
    }
    return data, meta_extra
