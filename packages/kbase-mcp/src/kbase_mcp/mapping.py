"""JSON <-> kbase DTO mapping shared by the `kb.*` tools (blueprint tree kbase-mcp/mapping.py).
Kept separate from `tools/dispatch.py`: this module is the M2 "no business logic" boundary —
it only reshapes flat MCP args/results, it never talks to the database itself."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from corelib.errors import ValidationError
from corelib.time import utc_now
from kbase.retrieval.query import RetrievalFilters, RetrievalQuery, RetrievalResult
from kbase.schemas import Collection, Jurisdiction, RetrievedChunk


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
    jurisdictions: list[Jurisdiction] | None = None,
) -> RetrievalQuery:
    """Maps flat `kb.search` tool args to a `RetrievalQuery` (allowlisted filters, WP05 §3).
    The agent always names the collections it searches (WP20 §4); regulatory text is
    searched as not expired today, in force or applying later (WP21 §2.2), unless
    `valid_at` asks what applied on a given day."""
    if not collections:
        raise ValidationError(
            "collections must name at least one collection", details={"collections": []}
        )
    not_expired_at = None
    if valid_at is None and "regulation" in collections:
        not_expired_at = utc_now().date()
    filters = RetrievalFilters(
        collections=list(dict.fromkeys(collections)),
        jurisdictions=list(dict.fromkeys(jurisdictions)) if jurisdictions else None,
        doc_types=doc_types,
        topics=topics,
        asset_classes=asset_classes,
        doc_keys=doc_keys,
        year_min=year_min,
        year_max=year_max,
        has_equations=has_equations,
        valid_at=valid_at,
        not_expired_at=not_expired_at,
    )
    return RetrievalQuery(text=text, k=k, filters=filters, strategy=strategy, rerank=rerank)


def _chunk_to_result(chunk: RetrievedChunk, today: date) -> dict[str, Any]:
    result: dict[str, Any] = {
        "rank": chunk.rank,
        "content": chunk.chunk.content,
        "kind": chunk.chunk.kind,
        "citation": chunk.citation.model_dump(mode="json"),
        "scores": chunk.scores,
    }
    valid_from = chunk.citation.valid_from
    if valid_from is not None and valid_from > today:
        result["note"] = f"not in force yet: applies from {valid_from.isoformat()}"
    if chunk.citation.doc_type == "proposal":
        result["note"] = "proposal, not in force"
    return result


def search_result_to_payload(result: RetrievalResult) -> tuple[dict[str, Any], dict[str, Any]]:
    """`(data, meta_extra)` for `kb.search`'s response envelope (WP06 §2)."""
    data = {
        "results": [_chunk_to_result(c, utc_now().date()) for c in result.chunks],
        "warnings": result.warnings,
    }
    provenance = sorted({c.citation.doc_key for c in result.chunks})
    meta_extra = {
        "strategy_used": result.strategy_used,
        "total_candidates": result.total_candidates,
        "provenance": provenance,
    }
    return data, meta_extra
