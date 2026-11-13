"""Retrieval DTOs (blueprint/03-INTERFACES.md §3.4)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from kbase.schemas import Collection, Jurisdiction, RetrievedChunk


class RetrievalFilters(BaseModel):
    """Allowlisted metadata filters; see `retrieval.filters.to_sql_predicate`."""

    # None searches every collection (CLI, eval); the MCP tool always names some (WP20 §4).
    collections: list[Collection] | None = None
    # Restricts regulatory documents only; other collections pass through (WP21 §3).
    jurisdictions: list[Jurisdiction] | None = None
    doc_types: list[str] | None = None
    topics: list[str] | None = None
    asset_classes: list[str] | None = None
    doc_keys: list[str] | None = None
    year_min: int | None = None
    year_max: int | None = None
    has_equations: bool | None = None
    valid_at: date | None = None
    # Not expired on that date: in force or applying later (WP21 §2.2). `valid_at` wins.
    not_expired_at: date | None = None


class RetrievalQuery(BaseModel):
    text: str
    k: int
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    strategy: Literal["hybrid", "vector", "lexical"] = "hybrid"
    rerank: bool = True


class RetrievalResult(BaseModel):
    query: RetrievalQuery
    chunks: list[RetrievedChunk]
    total_candidates: int
    strategy_used: Literal["hybrid", "vector", "lexical"]
    latency_ms: int
    correlation_id: str
    warnings: list[str] = Field(default_factory=list)
