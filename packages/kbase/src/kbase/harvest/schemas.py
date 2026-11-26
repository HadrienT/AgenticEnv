"""Typed records of the arXiv harvest (WP18)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from kbase.schemas import Collection


class ArxivEntry(BaseModel):
    """One paper as the arXiv API describes it. `arxiv_id` carries no version."""

    arxiv_id: str
    version: int
    title: str
    authors: list[str]
    abstract: str
    published: date
    updated: date
    primary_category: str
    categories: list[str]
    doi: str | None = None
    journal_ref: str | None = None


class HarvestQuery(BaseModel):
    """One arXiv search (API syntax) and the kbase topic its papers get."""

    topic: str
    query: str
    max_results: int = Field(default=50, ge=1, le=2000)
    asset_class: str | None = None


class HarvestProfile(BaseModel):
    name: str
    date_from: date | None = None
    date_to: date | None = None
    sort_by: Literal["relevance", "submittedDate", "lastUpdatedDate"] = "relevance"
    queries: list[HarvestQuery]
    # arXiv ids reviewed and rejected (off-topic): never harvested again.
    exclude_ids: list[str] = Field(default_factory=list)
    # Where the profile's papers go: the generated manifest (repo-relative; default the
    # config's `harvest.manifest`) and, when that manifest is new, its collection.
    manifest: str | None = None
    collection: Collection = "quant"


HarvestOutcome = Literal["converted", "no_html", "low_quality", "failed"]


class PaperResult(BaseModel):
    arxiv_id: str
    outcome: HarvestOutcome
    source: str | None = None  # html host the paper came from, or "cache"
    detail: str | None = None


class HarvestReport(BaseModel):
    profile: str
    dry_run: bool
    candidates: int
    skipped_known: int
    fetched: int
    from_cache: int
    converted: int
    no_html: int
    low_quality: int
    failed: int
    new_entries: int
    manifest: str
    papers: list[PaperResult]
