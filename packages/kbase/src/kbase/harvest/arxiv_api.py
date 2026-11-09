"""arXiv search API (Atom feed): query building, parsing, pagination (WP18 §2)."""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import date, datetime

from corelib.errors import DependencyError, ValidationError

from kbase.harvest.http import PoliteClient
from kbase.harvest.schemas import ArxivEntry, HarvestProfile, HarvestQuery

API_URL = "https://export.arxiv.org/api/query"
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}
_ID_RE = re.compile(r"arxiv\.org/abs/(?P<id>.+?)(?:v(?P<version>\d+))?$")
_WS_RE = re.compile(r"\s+")


def _clean(text: str | None) -> str:
    return _WS_RE.sub(" ", text or "").strip()


def parse_abs_url(url: str) -> tuple[str, int | None]:
    """`http://arxiv.org/abs/2502.17731v2` → (`2502.17731`, 2); old ids keep their slash."""
    match = _ID_RE.search(url.strip())
    if match is None:
        raise ValidationError(f"not an arXiv abs URL: {url}", details={"url": url})
    version = match.group("version")
    return match.group("id"), int(version) if version else None


def build_search_query(query: HarvestQuery, profile: HarvestProfile) -> str:
    """The profile's date window is ANDed to the query (`submittedDate:[… TO …]`)."""
    if profile.date_from is None and profile.date_to is None:
        return query.query
    start = (profile.date_from or date(1991, 1, 1)).strftime("%Y%m%d") + "0000"
    end = (profile.date_to or date(2999, 12, 31)).strftime("%Y%m%d") + "2359"
    return f"({query.query}) AND submittedDate:[{start} TO {end}]"


def build_url(search_query: str, *, start: int, max_results: int, sort_by: str) -> str:
    params = {
        "search_query": search_query,
        "start": str(start),
        "max_results": str(max_results),
        "sortBy": sort_by,
        "sortOrder": "descending",
    }
    return f"{API_URL}?{urllib.parse.urlencode(params)}"


def _parse_date(text: str | None) -> date:
    return datetime.fromisoformat(_clean(text).replace("Z", "+00:00")).date()


def parse_feed(xml_bytes: bytes) -> tuple[int, list[ArxivEntry]]:
    """(total results, entries). An API error comes back as a feed entry titled `Error`."""
    try:
        root = ET.fromstring(xml_bytes)  # noqa: S314 - the arXiv API, not user input
    except ET.ParseError as exc:
        raise DependencyError(f"arXiv API returned invalid XML: {exc}", details={}) from exc
    total = int(_clean(root.findtext("opensearch:totalResults", "0", _NS)) or 0)
    entries: list[ArxivEntry] = []
    for node in root.findall("atom:entry", _NS):
        title = _clean(node.findtext("atom:title", "", _NS))
        raw_id = _clean(node.findtext("atom:id", "", _NS))
        if title == "Error" and "/api/errors" in raw_id:
            message = _clean(node.findtext("atom:summary", "", _NS))
            raise ValidationError(f"arXiv API error: {message}", details={"id": raw_id})
        arxiv_id, version = parse_abs_url(raw_id)
        primary = node.find("arxiv:primary_category", _NS)
        entries.append(
            ArxivEntry(
                arxiv_id=arxiv_id,
                version=version or 1,
                title=title,
                authors=[
                    _clean(a.findtext("atom:name", "", _NS))
                    for a in node.findall("atom:author", _NS)
                ],
                abstract=_clean(node.findtext("atom:summary", "", _NS)),
                published=_parse_date(node.findtext("atom:published", None, _NS)),
                updated=_parse_date(node.findtext("atom:updated", None, _NS)),
                primary_category=primary.get("term", "") if primary is not None else "",
                categories=[
                    c.get("term", "") for c in node.findall("atom:category", _NS) if c.get("term")
                ],
                doi=_clean(node.findtext("arxiv:doi", "", _NS)) or None,
                journal_ref=_clean(node.findtext("arxiv:journal_ref", "", _NS)) or None,
            )
        )
    return total, entries


def search(
    client: PoliteClient, query: HarvestQuery, profile: HarvestProfile, *, page_size: int
) -> Iterator[ArxivEntry]:
    """Up to `query.max_results` entries, page by page; stops early on a short page."""
    search_query = build_search_query(query, profile)
    yielded = 0
    start = 0
    while yielded < query.max_results:
        size = min(page_size, query.max_results - yielded)
        url = build_url(search_query, start=start, max_results=size, sort_by=profile.sort_by)
        response = client.get(url)
        if response.status != 200:
            raise DependencyError(
                f"arXiv API returned HTTP {response.status}",
                details={"url": url, "status": response.status},
            )
        total, entries = parse_feed(response.body)
        for entry in entries[: query.max_results - yielded]:
            yield entry
            yielded += 1
        start += len(entries)
        if len(entries) < size or start >= total:
            return
