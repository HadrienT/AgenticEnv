from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml
from corelib.errors import DependencyError
from kbase.harvest.basel import (
    chapter_refs,
    convert_chapter,
    harvest_basel,
    topic_for,
    upsert_manifest,
)
from kbase.harvest.http import RawResponse
from kbase.ingestion.chunking import SectionChunker
from kbase.ingestion.parsers.markdown import MarkdownParser
from kbase.ingestion.sources import resolve
from kbase.schemas import ChunkPolicy, DocumentMeta

_HTML = (Path(__file__).parent / "fixtures" / "basel" / "chapter.html").read_text()


def test_chapter_refs_lists_each_chapter_once_with_its_dates() -> None:
    refs = chapter_refs(_HTML)
    assert [r.code for r in refs] == ["MAR20", "MAR21", "CRE52"]
    mar21 = refs[1]
    assert mar21.standard == "MAR" and mar21.title.startswith("Standardised approach: sens")
    assert mar21.in_force == date(2023, 1, 1) and mar21.published == date(2026, 3, 23)
    assert mar21.url.startswith("https://www.bis.org/committees/bcbs/basel-framework/")


def test_convert_chapter_writes_a_heading_per_paragraph() -> None:
    conversion = convert_chapter(_HTML, "MAR21")
    md = conversion.markdown
    assert md.startswith("# MAR21 Standardised approach: sensitivities-based method\n")
    assert conversion.effective == date(2023, 1, 1)
    assert conversion.paragraphs == 2 and conversion.formulas == 1
    assert (conversion.tables, conversion.footnotes, conversion.faqs) == (1, 1, 1)
    assert "## Process to calculate the capital requirement" in md
    assert "### Delta and vega risk capital requirement" in md
    assert "#### MAR21.3\n\nAs set out in MAR21.1, the requirement" in md
    assert "(1) Determine the net sensitivity s_{k}." in md
    assert "(2) Aggregate within the bucket: [formula: MAR21_20220101_3.svg]" in md
    assert "(a) with correlation from the table[^1]" in md
    assert "| Tenor | Risk weight |" in md and "| 0.25 year | 1.7% |" in md
    assert "[^1]: Correlations are set out in MAR21.45." in md
    assert "FAQ1: May a bank use market rate sensitivities?\n\nNo, zero rate sensitivities." in md


def test_converted_chapter_chunks_carry_paragraph_ids(tmp_path: Path) -> None:
    path = tmp_path / "MAR21.md"
    path.write_text(convert_chapter(_HTML, "MAR21").markdown)
    doc = MarkdownParser().parse(
        path, DocumentMeta(doc_key="bcbs-mar21", title="MAR21", doc_type="standard")
    )
    chunks = SectionChunker().chunk(
        doc,
        ChunkPolicy(
            strategy="section", target_tokens=60, max_tokens=200, min_tokens=5, overlap_tokens=0
        ),
    )
    ids = [pid for chunk in chunks for pid in chunk.paragraph_ids]
    assert list(dict.fromkeys(ids)) == ["MAR21.3", "MAR21.4"]  # 21.4 may span chunks
    para4 = next(c for c in chunks if c.paragraph_ids == ["MAR21.4"])
    assert para4.content.startswith("#### MAR21.4")
    assert any("FAQ1" in c.content for c in chunks if "MAR21.4" in c.paragraph_ids)


def test_convert_rejects_a_page_that_is_not_a_chapter() -> None:
    with pytest.raises(ValueError, match="chapters-content"):
        convert_chapter("<html><body>nothing</body></html>", "MAR21")


def test_topics_by_chapter_then_standard() -> None:
    assert topic_for("CRE52", "CRE") == "reg-ccr-sa-ccr"
    assert topic_for("MAR50", "MAR") == "reg-cva-capital"
    assert topic_for("LCR30", "LCR") == "reg-liquidity"
    assert topic_for("XYZ1", "XYZ") == "reg-other"


def test_upsert_manifest_replaces_by_doc_key_and_keeps_others(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest-regulation.yaml"
    upsert_manifest(manifest, [{"doc_key": "a", "path": "a.md"}, {"doc_key": "b", "path": "b"}])
    added, replaced = upsert_manifest(manifest, [{"doc_key": "a", "path": "a2.md"}])
    data = yaml.safe_load(manifest.read_text())
    assert (added, replaced) == (0, 1)
    assert data["collection"] == "regulation"
    assert [d["path"] for d in data["documents"]] == ["a2.md", "b"]


class _FakeClient:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.requests_made = 0
        self.urls: list[str] = []

    def get(self, url: str) -> RawResponse:
        self.requests_made += 1
        self.urls.append(url)
        body = self.pages.get(url)
        return RawResponse(status=200 if body else 404, url=url, body=(body or "").encode())


def test_harvest_fetches_converts_and_writes_an_ingestible_manifest(tmp_path: Path) -> None:
    seed = "https://www.bis.org/seed"
    refs = {r.code: r for r in chapter_refs(_HTML)}
    client = _FakeClient({seed: _HTML, refs["MAR21"].url: _HTML})
    manifest = tmp_path / "manifest-regulation.yaml"
    report = harvest_basel(
        client,
        seed_url=seed,
        standards=["MAR"],
        chapters=[],
        documents_dir=tmp_path,
        html_dir="basel/html",
        md_dir="basel/md",
        manifest=manifest,
    )
    assert report.chapters_selected == ["MAR20", "MAR21"]
    assert report.converted == ["MAR21"] and report.failed == {"MAR20": "HTTP 404"}
    assert (tmp_path / "basel/md/MAR21.md").read_text().startswith("# MAR21")
    (item,) = resolve(manifest, tmp_path)
    assert item.meta.doc_key == "bcbs-mar21" and item.meta.collection == "regulation"
    assert item.meta.doc_type == "standard" and item.meta.topic == "reg-frtb-sa"
    assert item.valid_from == date(2023, 1, 1)
    assert "/sites/default/files/" not in " ".join(client.urls)  # robots.txt


def test_harvest_dry_run_fetches_only_the_seed(tmp_path: Path) -> None:
    client = _FakeClient({"https://www.bis.org/seed": _HTML})
    report = harvest_basel(
        client,
        seed_url="https://www.bis.org/seed",
        standards=[],
        chapters=["CRE52"],
        documents_dir=tmp_path,
        html_dir="h",
        md_dir="m",
        manifest=tmp_path / "m.yaml",
        dry_run=True,
    )
    assert report.chapters_selected == ["CRE52"] and client.requests_made == 1
    assert not (tmp_path / "m.yaml").exists()


def test_harvest_fails_loudly_when_the_seed_is_gone(tmp_path: Path) -> None:
    with pytest.raises(DependencyError):
        harvest_basel(
            _FakeClient({}),
            seed_url="https://www.bis.org/seed",
            standards=["MAR"],
            chapters=[],
            documents_dir=tmp_path,
            html_dir="h",
            md_dir="m",
            manifest=tmp_path / "m.yaml",
        )


def test_chapter_refs_keep_the_latest_publication_of_a_chapter() -> None:
    from kbase.harvest.basel import chapter_refs

    base = "/committees/bcbs/basel-framework/standard/cap/10/inforce/2019-12-15/published/"
    html = "".join(
        f'<a href="{base}{day}"><span class="accordion-subitem__label">CAP10 Definition</span></a>'
        for day in ("2019-12-15", "2020-06-05", "2019-12-15")
    )
    (ref,) = chapter_refs(html)
    assert ref.url.endswith("/published/2020-06-05") and ref.published.year == 2020


def test_harvest_follows_a_newer_publication_linked_from_the_chapter_page(
    tmp_path: Path,
) -> None:
    seed = "https://www.bis.org/seed"
    current = {r.code: r for r in chapter_refs(_HTML)}["MAR21"]
    older_html = _HTML.replace("published/2026-03-23", "published/2025-01-01")
    older_url = current.url.replace("published/2026-03-23", "published/2025-01-01")
    # The old page links the current publication, as bis.org does.
    client = _FakeClient({seed: older_html, older_url: _HTML, current.url: _HTML})
    report = harvest_basel(
        client,
        seed_url=seed,
        standards=[],
        chapters=["MAR21"],
        documents_dir=tmp_path,
        html_dir="basel/html",
        md_dir="basel/md",
        manifest=tmp_path / "manifest-regulation.yaml",
    )
    assert report.converted == ["MAR21"]
    assert client.urls == [seed, older_url, current.url]
    (item,) = resolve(tmp_path / "manifest-regulation.yaml", tmp_path)
    assert item.meta.source_url == current.url
