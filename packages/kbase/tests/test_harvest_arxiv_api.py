from __future__ import annotations

import urllib.parse
from datetime import date
from pathlib import Path

import pytest
from corelib.errors import DependencyError, ValidationError
from kbase.harvest import arxiv_api
from kbase.harvest.http import PoliteClient, RawResponse
from kbase.harvest.schemas import HarvestProfile, HarvestQuery

FIXTURES = Path(__file__).parent / "fixtures" / "harvest"


def _profile(**kwargs: object) -> HarvestProfile:
    return HarvestProfile.model_validate({"name": "p", "queries": [], **kwargs})


def test_parse_abs_url_new_old_and_unversioned() -> None:
    assert arxiv_api.parse_abs_url("http://arxiv.org/abs/2401.00001v2") == ("2401.00001", 2)
    assert arxiv_api.parse_abs_url("http://arxiv.org/abs/math/0501001v1") == ("math/0501001", 1)
    assert arxiv_api.parse_abs_url("https://arxiv.org/abs/2401.00001") == ("2401.00001", None)
    with pytest.raises(ValidationError):
        arxiv_api.parse_abs_url("https://example.com/paper")


def test_date_window_is_anded_to_the_query() -> None:
    query = HarvestQuery(topic="t", query="abs:Heston")
    assert arxiv_api.build_search_query(query, _profile()) == "abs:Heston"
    windowed = arxiv_api.build_search_query(query, _profile(date_from="2020-01-01"))
    assert windowed == "(abs:Heston) AND submittedDate:[202001010000 TO 299912312359]"


def test_parse_feed_reads_entries() -> None:
    total, entries = arxiv_api.parse_feed((FIXTURES / "feed.xml").read_bytes())
    assert total == 2
    first, old = entries
    assert first.arxiv_id == "2401.00001" and first.version == 2
    assert first.title == "Multilevel Monte Carlo for Barrier Options"
    assert first.authors == ["Ada Lovelace", "Alan Turing"]
    assert first.abstract == "We price barrier options with MLMC."
    assert first.published == date(2024, 1, 1)
    assert first.primary_category == "q-fin.CP"
    assert first.categories == ["q-fin.CP", "math.NA"]
    assert first.doi == "10.1000/xyz" and first.journal_ref is None
    assert old.arxiv_id == "math/0501001"


def test_parse_feed_raises_on_api_error_entry() -> None:
    with pytest.raises(ValidationError, match="malformed query"):
        arxiv_api.parse_feed((FIXTURES / "error.xml").read_bytes())


def test_parse_feed_rejects_invalid_xml() -> None:
    with pytest.raises(DependencyError):
        arxiv_api.parse_feed(b"<not xml")


class _PagedTransport:
    """Serves the fixture feed for any page, recording the requested URLs."""

    def __init__(self, status: int = 200) -> None:
        self.urls: list[str] = []
        self.status = status

    def fetch(self, url: str, *, headers: dict[str, str], timeout_s: float) -> RawResponse:
        self.urls.append(url)
        return RawResponse(status=self.status, url=url, body=(FIXTURES / "feed.xml").read_bytes())


def _client(transport: _PagedTransport) -> PoliteClient:
    return PoliteClient(
        user_agent="test", min_interval_s=0, max_attempts=1, timeout_s=1,
        transport=transport, sleep=lambda _s: None,
    )  # fmt: skip


def test_search_stops_at_max_results_and_sends_paging_params() -> None:
    transport = _PagedTransport()
    query = HarvestQuery(topic="t", query="abs:MLMC", max_results=1)
    entries = list(arxiv_api.search(_client(transport), query, _profile(), page_size=100))
    assert [e.arxiv_id for e in entries] == ["2401.00001"]
    params = urllib.parse.parse_qs(urllib.parse.urlparse(transport.urls[0]).query)
    assert params["max_results"] == ["1"] and params["start"] == ["0"]
    assert params["search_query"] == ["abs:MLMC"]


def test_search_stops_when_total_is_reached() -> None:
    transport = _PagedTransport()
    query = HarvestQuery(topic="t", query="abs:MLMC", max_results=50)
    entries = list(arxiv_api.search(_client(transport), query, _profile(), page_size=2))
    assert len(entries) == 2 and len(transport.urls) == 1


def test_search_raises_on_http_error() -> None:
    query = HarvestQuery(topic="t", query="abs:MLMC")
    with pytest.raises(DependencyError):
        list(
            arxiv_api.search(_client(_PagedTransport(status=400)), query, _profile(), page_size=10)
        )
