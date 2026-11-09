"""`harvest`: profile → arXiv entries → cached LaTeXML HTML → kbase Markdown → manifest.

Ingestion is left to `kbase ingest` on the generated manifest (WP18 §2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from corelib.errors import AppError
from corelib.logging import get_logger

from kbase.harvest import arxiv_api, latexml
from kbase.harvest.http import PoliteClient
from kbase.harvest.manifest import (
    append_entries,
    build_entry,
    known_arxiv_ids,
    markdown_path,
    safe_id,
)
from kbase.harvest.schemas import (
    ArxivEntry,
    HarvestProfile,
    HarvestQuery,
    HarvestReport,
    PaperResult,
)

logger = get_logger(__name__)

NATIVE_HTML_URL = "https://arxiv.org/html/{id}"
AR5IV_HTML_URL = "https://ar5iv.labs.arxiv.org/html/{id}"
_LATEXML_MARKER = "ltx_document"
_NO_HTML_SUFFIX = ".none"


@dataclass(frozen=True)
class HarvestSettings:
    documents_dir: Path
    manifest: Path
    known_manifests: tuple[Path, ...]
    html_dir: str
    md_dir: str
    page_size: int
    min_text_chars: int


def _fetch_html(client: PoliteClient, arxiv_id: str) -> tuple[str | None, str | None]:
    """(html, host): native arXiv HTML first, then ar5iv; (None, None) if neither has it.

    ar5iv redirects to the abs page when it has no conversion, hence the marker check."""
    for template, host in ((NATIVE_HTML_URL, "arxiv.org"), (AR5IV_HTML_URL, "ar5iv")):
        response = client.get(template.format(id=arxiv_id))
        if response.status == 200 and "/html/" in response.url:
            html = response.body.decode("utf-8", errors="replace")
            if _LATEXML_MARKER in html:
                return html, host
    return None, None


def _cached_html(
    client: PoliteClient, arxiv_id: str, html_dir: Path
) -> tuple[str | None, str | None]:
    """(html, source) from the cache, else fetched and cached; misses are cached too."""
    html_path = html_dir / f"{safe_id(arxiv_id)}.html"
    miss_path = html_dir / f"{safe_id(arxiv_id)}{_NO_HTML_SUFFIX}"
    if html_path.is_file():
        return html_path.read_text(encoding="utf-8"), "cache"
    if miss_path.is_file():
        return None, "cache"
    html, host = _fetch_html(client, arxiv_id)
    html_dir.mkdir(parents=True, exist_ok=True)
    if html is None:
        miss_path.touch()
        return None, "remote"
    html_path.write_text(html, encoding="utf-8")
    return html, host


def _candidates(
    client: PoliteClient, profile: HarvestProfile, page_size: int
) -> list[tuple[ArxivEntry, HarvestQuery]]:
    """Entries of every query, deduplicated: the first query to find a paper sets its topic."""
    seen: set[str] = set()
    found: list[tuple[ArxivEntry, HarvestQuery]] = []
    for query in profile.queries:
        count = 0
        for entry in arxiv_api.search(client, query, profile, page_size=page_size):
            count += 1
            if entry.arxiv_id not in seen:
                seen.add(entry.arxiv_id)
                found.append((entry, query))
        logger.info("harvest query done", extra={"topic": query.topic, "results": count})
    return found


def harvest(
    profile: HarvestProfile,
    *,
    client: PoliteClient,
    settings: HarvestSettings,
    max_new: int | None = None,
    dry_run: bool = False,
) -> HarvestReport:
    known = known_arxiv_ids(settings.known_manifests)
    candidates = _candidates(client, profile, settings.page_size)
    fresh = [(e, q) for e, q in candidates if e.arxiv_id not in known]
    if max_new is not None:
        fresh = fresh[:max_new]

    papers: list[PaperResult] = []
    entries: list[dict[str, Any]] = []
    html_dir = settings.documents_dir / settings.html_dir
    for entry, query in [] if dry_run else fresh:
        try:
            html, source = _cached_html(client, entry.arxiv_id, html_dir)
            if html is None:
                papers.append(
                    PaperResult(arxiv_id=entry.arxiv_id, outcome="no_html", source=source)
                )
                continue
            conversion = latexml.convert(html, title=entry.title, abstract=entry.abstract)
            if conversion.sections == 0 or conversion.text_chars < settings.min_text_chars:
                papers.append(
                    PaperResult(
                        arxiv_id=entry.arxiv_id,
                        outcome="low_quality",
                        source=source,
                        detail=f"sections={conversion.sections} chars={conversion.text_chars}",
                    )
                )
                continue
            md_rel = markdown_path(entry.arxiv_id, settings.md_dir)
            md_file = settings.documents_dir / md_rel
            md_file.parent.mkdir(parents=True, exist_ok=True)
            md_file.write_text(conversion.markdown, encoding="utf-8")
            entries.append(build_entry(entry, query, md_dir=settings.md_dir))
            papers.append(
                PaperResult(
                    arxiv_id=entry.arxiv_id,
                    outcome="converted",
                    source=source,
                    detail=f"sections={conversion.sections} equations={conversion.equations}",
                )
            )
        except AppError as exc:
            logger.error("harvest paper failed", extra={"arxiv_id": entry.arxiv_id})
            papers.append(
                PaperResult(arxiv_id=entry.arxiv_id, outcome="failed", detail=exc.message)
            )

    added = 0 if dry_run else append_entries(settings.manifest, entries)
    by_outcome = {o: sum(1 for p in papers if p.outcome == o) for o in
                  ("converted", "no_html", "low_quality", "failed")}  # fmt: skip
    return HarvestReport(
        profile=profile.name,
        dry_run=dry_run,
        candidates=len(fresh),
        skipped_known=len(candidates) - len([c for c in candidates if c[0].arxiv_id not in known]),
        fetched=sum(1 for p in papers if p.source not in (None, "cache")),
        from_cache=sum(1 for p in papers if p.source == "cache"),
        converted=by_outcome["converted"],
        no_html=by_outcome["no_html"],
        low_quality=by_outcome["low_quality"],
        failed=by_outcome["failed"],
        new_entries=added,
        manifest=str(settings.manifest),
        papers=papers,
    )
