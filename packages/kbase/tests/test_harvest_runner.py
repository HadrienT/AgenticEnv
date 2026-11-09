from __future__ import annotations

from pathlib import Path

import yaml
from kbase.harvest.http import PoliteClient, RawResponse
from kbase.harvest.runner import HarvestSettings, harvest
from kbase.harvest.schemas import HarvestProfile
from kbase.ingestion import sources

FIXTURES = Path(__file__).parent / "fixtures" / "harvest"
_FEED = (FIXTURES / "feed.xml").read_bytes()
_PAPER = (FIXTURES / "paper.html").read_bytes()


class _Web:
    """Fake arXiv: the API serves the fixture feed; HTML per URL, else 404."""

    def __init__(self, pages: dict[str, RawResponse]) -> None:
        self.pages = pages
        self.urls: list[str] = []

    def fetch(self, url: str, *, headers: dict[str, str], timeout_s: float) -> RawResponse:
        self.urls.append(url)
        if url.startswith("https://export.arxiv.org/api/query"):
            return RawResponse(status=200, url=url, body=_FEED)
        return self.pages.get(url, RawResponse(status=404, url=url, body=b""))

    def html_requests(self) -> list[str]:
        return [u for u in self.urls if "/html/" in u]


def _html(url: str, body: bytes = _PAPER) -> RawResponse:
    return RawResponse(status=200, url=url, body=body)


def _run(
    tmp_path: Path, web: _Web, *, dry_run: bool = False, known: tuple[Path, ...] = ()
) -> tuple[object, HarvestSettings]:
    manifest = tmp_path / "repo" / "manifest-arxiv.yaml"
    settings = HarvestSettings(
        documents_dir=tmp_path / "docs",
        manifest=manifest,
        known_manifests=(manifest, *known),
        html_dir="arxiv/html",
        md_dir="arxiv/md",
        page_size=100,
        min_text_chars=50,
    )
    profile = HarvestProfile.model_validate(
        {"name": "p", "queries": [{"topic": "numerical-mc", "query": "abs:x", "max_results": 10}]}
    )
    client = PoliteClient(
        user_agent="t", min_interval_s=0, max_attempts=1, timeout_s=1,
        transport=web, sleep=lambda _s: None,
    )  # fmt: skip
    return harvest(profile, client=client, settings=settings, dry_run=dry_run), settings


def test_native_then_ar5iv_then_no_html(tmp_path: Path) -> None:
    web = _Web(
        {
            "https://arxiv.org/html/2401.00001": _html("https://arxiv.org/html/2401.00001"),
            # ar5iv without a conversion redirects to the abs page.
            "https://ar5iv.labs.arxiv.org/html/math/0501001": _html(
                "https://arxiv.org/abs/math/0501001", b"<html>abs page</html>"
            ),
        }
    )
    report, settings = _run(tmp_path, web)
    outcomes = {p.arxiv_id: (p.outcome, p.source) for p in report.papers}  # type: ignore[attr-defined]
    assert outcomes == {
        "2401.00001": ("converted", "arxiv.org"),
        "math/0501001": ("no_html", "remote"),
    }
    md = settings.documents_dir / "arxiv/md/2401.00001.md"
    assert md.read_text(encoding="utf-8").startswith("# Multilevel Monte Carlo for Barrier Options")
    assert (settings.documents_dir / "arxiv/html/math_0501001.none").is_file()


def test_manifest_is_accepted_by_ingest_and_rerun_fetches_nothing(tmp_path: Path) -> None:
    web = _Web({"https://arxiv.org/html/2401.00001": _html("https://arxiv.org/html/2401.00001")})
    report, settings = _run(tmp_path, web)
    assert report.new_entries == 1  # type: ignore[attr-defined]
    items = sources.resolve(settings.manifest, settings.documents_dir)
    assert [i.meta.doc_key for i in items] == ["arxiv-2401.00001"]
    meta = items[0].meta
    assert meta.topic == "numerical-mc" and meta.year == 2024
    assert meta.source_url == "https://arxiv.org/abs/2401.00001v2"

    html_before = len(web.html_requests())
    rerun, _ = _run(tmp_path, web)
    assert rerun.skipped_known == 1 and rerun.new_entries == 0  # type: ignore[attr-defined]
    # The converted paper is known; the miss is served from its cached marker.
    assert len(web.html_requests()) == html_before
    assert [p.source for p in rerun.papers] == ["cache"]  # type: ignore[attr-defined]


def test_papers_in_other_manifests_are_skipped(tmp_path: Path) -> None:
    existing = tmp_path / "manifest.yaml"
    existing.write_text(
        yaml.safe_dump(
            {"documents": [{"doc_key": "mlmc", "source_url": "https://arxiv.org/abs/2401.00001"}]}
        )
    )
    report, _ = _run(tmp_path, _Web({}), known=(existing,))
    assert report.skipped_known == 1  # type: ignore[attr-defined]
    assert [p.arxiv_id for p in report.papers] == ["math/0501001"]  # type: ignore[attr-defined]


def test_low_quality_conversion_is_rejected(tmp_path: Path) -> None:
    url = "https://arxiv.org/html/2401.00001"
    web = _Web({url: _html(url, b'<article class="ltx_document"><p>tiny</p></article>')})
    report, settings = _run(tmp_path, web)
    first = report.papers[0]  # type: ignore[attr-defined]
    assert first.outcome == "low_quality"
    assert not settings.manifest.exists()


def test_dry_run_fetches_no_html_and_writes_nothing(tmp_path: Path) -> None:
    web = _Web({})
    report, settings = _run(tmp_path, web, dry_run=True)
    assert report.candidates == 2 and report.papers == []  # type: ignore[attr-defined]
    assert web.html_requests() == []
    assert not settings.manifest.exists() and not settings.documents_dir.exists()
