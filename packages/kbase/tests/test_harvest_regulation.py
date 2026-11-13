# ruff: noqa: E501  (HTML fixtures copied from the sources)
"""WP21: EU, UK and US rule converters, catalogue, harvest run with a fake client."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
import yaml
from corelib.errors import ValidationError
from kbase.harvest.http import RawResponse
from kbase.harvest.regulation import (
    Catalog,
    _CfrPath,
    article_selected,
    convert_ecfr,
    convert_eu,
    convert_pra,
    harvest_regulation,
    load_catalog,
)
from kbase.ingestion.parsers.markdown import MarkdownParser
from kbase.regulatory import paragraph_id
from kbase.schemas import DocumentMeta

_ECFR = """<?xml version="1.0" encoding="UTF-8"?>
<DIV8 N="217.132" TYPE="SECTION">
<HEAD>§ 217.132 Counterparty credit risk of OTC derivative contracts.</HEAD>
<P>(a) <I>Methodologies.</I> (1) A Board-regulated institution may use:</P>
<P>(i) The collateral haircut approach; and</P>
<P>(ii) The internal models methodology.</P>
<P>(b) <I>EAD for margin loans</I>—(1) <I>General.</I> An institution may recognize collateral.</P>
<P>(2) <I>Haircuts.</I> (i) EAD equals:</P>
<FP-2>max{0, [(ΣE − ΣC) + Σ(E<E T="52">s</E> × H<E T="52">s</E>)]}</FP-2>
<P>(A) ΣE equals the value of the exposure <img src="/graphics/er24ja20.025.gif">;</P>
<P>(<I>1</I>) First italic level;</P>
<img src="/graphics/er11oc13.031.gif">
<P>(<I>2</I>)(<I>i</I>) Two markers at once.</P>
<DIV><TABLE><TR><TH>Maturity</TH><TH colspan="2">Haircut</TH></TR>
<TR><TD>1 year</TD><TD>0.5</TD><TD>1.0</TD></TR></TABLE></DIV>
<CITA>[78 FR 62157]</CITA>
</DIV8>
"""

_IMG = base64.b64encode(b"\xff\xd8\xff fake jpeg").decode()
_EU = f"""<html><body>
<p class="title-division-1">CHAPTER 6</p>
<p class="title-division-2">Counterparty credit risk</p>
<div class="eli-subdivision" id="art_273">
  <p class="title-article-norm">Article 273</p>
  <div class="eli-title"><p class="stitle-article-norm">Methods</p></div>
  <p class="norm">Out of range.</p>
</div>
<div class="eli-subdivision" id="art_274">
  <p class="title-article-norm">Article 274</p>
  <div class="eli-title"><p class="stitle-article-norm">Exposure value</p></div>
  <div class="norm"><span class="no-parag">1.  </span>
    <div class="norm inline-element"><p class="norm inline-element">Where:</p>
      <div class="grid-container grid-list">
        <div class="list grid-list-column-1"><span>(a) </span></div>
        <div class="grid-list-column-2"><p class="norm">the netting agreement belongs to Article 295;</p></div>
      </div>
    </div>
  </div>
  <div class="norm"><span class="no-parag">2.  </span>
    <div class="norm inline-element"><p class="norm">Exposure value = α · (RC + PFE)</p>
      <table><tr><td><p class="norm">RC</p></td><td><p class="norm">=</p></td>
      <td><p class="norm">the replacement cost;</p></td></tr></table>
      <p class="norm">with <img src="data:image/jpg;base64,{_IMG}"/> the supervisory factor <span class="modref">▼M8</span></p>
    </div>
  </div>
</div>
<div class="eli-subdivision" id="art_274a">
  <p class="title-article-norm">Article 274a</p>
  <p class="norm">Inserted article.</p>
</div>
</body></html>"""

_PRA = """<html><body>
<div class="chapter-section"><div class="div-row">
  <div class="div-row__col-1"><p><span class="rule-number rule-number--mega chapter-number">2</span></p></div>
  <div class="div-row__col-2"><h3 class="header-sans chapter-heading">Level of Application</h3></div>
</div></div>
<div class="row-block row-block--border"><div class="div-row">
  <div class="div-row__col-1"><p><span class="rule-number">2.1</span></p></div>
  <div class="div-row__col-2 "><p>A firm must apply this Part on an individual basis.</p></div>
</div><div class="row-block__info"><ul><li>01/01/2027</li></ul></div></div>
<div class="chapter-section"><div class="div-row">
  <div class="div-row__col-1"><p><span class="rule-number"></span></p></div>
  <div class="div-row__col-2"><h3 class="header-sans chapter-heading">Article 325f Own Funds Requirements</h3></div>
</div></div>
<div class="row-block row-block--border"><div class="div-row">
  <div class="div-row__col-1"><p><span class="rule-number">1.</span></p></div>
  <div class="div-row__col-2 "><p>[Note: Provision left blank]</p></div>
</div></div>
<div class="row-block row-block--border"><div class="div-row">
  <div class="div-row__col-1"><p><span class="rule-number">7.</span></p></div>
  <div class="div-row__col-2 "><p>Weighted sensitivities are aggregated (<em>&rho;<sub>kl</sub></em>):</p>
  <p style="text-align: center;">\\[K_b=\\sqrt{\\sum_{k}{WS_k^2}}\\]</p>
  <p><img src="-/media/27cc8d666e6a46d7967e6407cad7d37b.ashx" width="550"></p>
  <ol class="new-bullet"><li><span>(a) first item;</span></li></ol>
  <span class="visually-hidden">hidden</span></div>
</div></div>
</body></html>"""


def _ids(markdown: str) -> list[str | None]:
    return [
        paragraph_id(line.lstrip("#").strip())
        for line in markdown.splitlines()
        if line.startswith("##")
    ]


def test_ecfr_paragraph_paths_headings_formulas_and_tables() -> None:
    conv = convert_ecfr(_ECFR, title="12 CFR 217.132")
    ids = _ids(conv.markdown)
    assert ids == [
        "§ 217.132", "§ 217.132(a)", "§ 217.132(a)(1)", "§ 217.132(a)(1)(i)",
        "§ 217.132(a)(1)(ii)", "§ 217.132(b)", "§ 217.132(b)(1)", "§ 217.132(b)(2)",
        "§ 217.132(b)(2)(i)", "§ 217.132(b)(2)(i)(A)", "§ 217.132(b)(2)(i)(A)(1)",
        "§ 217.132(b)(2)(i)(A)(2)(i)",
    ]  # fmt: skip
    assert "#### § 217.132(b) EAD for margin loans" in conv.markdown
    assert "Σ(E_{s} × H_{s})" in conv.markdown
    assert "| Maturity | Haircut |  |" in conv.markdown and conv.tables == 1
    assert "78 FR" not in conv.markdown
    assert "[formula: er24ja20.025.gif]" in conv.markdown
    assert conv.image_urls == {
        "er24ja20.025.gif": "https://www.ecfr.gov/graphics/er24ja20.025.gif",
        "er11oc13.031.gif": "https://www.ecfr.gov/graphics/er11oc13.031.gif",
    }


def test_cfr_roman_numeral_after_h_is_a_letter() -> None:
    path = _CfrPath()
    assert path.push("h", italic=False) == "(h)"
    assert path.push("i", italic=False) == "(i)"  # the letter after (h)
    path = _CfrPath()
    path.push("h", italic=False)
    path.push("1", italic=False)
    assert path.push("i", italic=False) == "(h)(1)(i)"  # roman under (1)


def test_eu_articles_in_range_with_paragraphs_lists_definitions_and_images() -> None:
    conv = convert_eu(_EU, title="CRR CCR", doc_key="eu-x", articles=["274-274a"])
    md = conv.markdown
    assert _ids(md)[1:] == ["Article 274", "Article 274(1)", "Article 274(2)", "Article 274a"]
    assert "## CHAPTER 6 Counterparty credit risk" in md
    assert "Out of range" not in md
    assert "(a) the netting agreement belongs to Article 295;" in md
    assert "RC = the replacement cost;" in md
    assert "[formula: eu-x-001.jpg]" in md and conv.images["eu-x-001.jpg"].startswith(b"\xff\xd8")
    assert "▼M8" not in md


def test_eu_article_ranges_follow_inserted_numbering() -> None:
    assert article_selected("325c", ["325c-325ay"])
    assert article_selected("325ay", ["325c-325ay"])
    assert article_selected("325k", ["325c-325ay"])
    assert not article_selected("325az", ["325c-325ay"])
    assert not article_selected("325b", ["325c-325ay"])
    assert article_selected("106", ["102-104c", "106"]) and not article_selected(
        "105", ["102-104c", "106"]
    )


def test_pra_rules_articles_latex_and_skipped_provisions() -> None:
    conv = convert_pra(_PRA, title="PRA Market Risk")
    md = conv.markdown
    assert _ids(md) == [None, "Rule 2.1", "Article 325f", "Article 325f(7)"]
    assert "## 2 Level of Application" in md
    assert "$$\nK_b=\\sqrt{\\sum_{k}{WS_k^2}}\n$$" in md and conv.formulas == 2
    assert "[formula: pra-27cc8d666e6a46d7967e6407cad7d37b.jpg]" in md
    assert conv.image_urls == {
        "pra-27cc8d666e6a46d7967e6407cad7d37b.jpg": (
            "https://www.prarulebook.co.uk/-/media/27cc8d666e6a46d7967e6407cad7d37b.ashx"
        )
    }
    assert "ρ_{kl}" in md and "(a) first item;" in md
    assert "Provision left blank" not in md and "hidden" not in md and "01/01/2027" not in md


def test_converted_markdown_parses_into_paragraph_sections(tmp_path: Path) -> None:
    for name, conv in (
        ("pra.md", convert_pra(_PRA, title="PRA Market Risk")),
        ("eu.md", convert_eu(_EU, title="CRR", doc_key="eu-x", articles=["274"])),
        ("us.md", convert_ecfr(_ECFR, title="12 CFR 217.132")),
    ):
        path = tmp_path / name
        path.write_text(conv.markdown, encoding="utf-8")
        parsed = MarkdownParser().parse(
            path, DocumentMeta(doc_key=name, title=name, doc_type="law", collection="regulation")
        )
        ids = {paragraph_id(s.title) for s in parsed.sections} - {None}
        assert ids, name
        if name == "pra.md":
            assert "Article 325f(7)" in ids
            assert any(b.kind == "equation" for b in parsed.blocks)


_CATALOG = {
    "documents": [
        {
            "doc_key": "uk-x", "source": "pra", "jurisdiction": "uk", "pra_part": "market-risk",
            "pra_date": "2027-01-01", "title": "UK X", "authors": ["PRA"], "topic": "reg-frtb-sa",
            "license": "l", "valid_from": "2027-01-01",
        },
        {
            "doc_key": "eu-x", "source": "eu", "jurisdiction": "eu", "celex": "02013R0575-20260626",
            "articles": ["274-274a"], "title": "EU X", "authors": ["EP"], "topic": "reg-ccr",
            "license": "l",
        },
        {
            "doc_key": "eu-y", "source": "eu", "jurisdiction": "eu", "celex": "02013R0575-20260626",
            "articles": ["273"], "title": "EU Y", "authors": ["EP"], "topic": "reg-ccr",
            "license": "l",
        },
        {
            "doc_key": "us-x", "source": "ecfr", "jurisdiction": "us", "cfr_title": 12,
            "part": "217", "sections": ["217.132"], "title": "US X", "authors": ["Fed"],
            "topic": "reg-ccr", "license": "l",
        },
    ]
}  # fmt: skip


def test_catalogue_requires_the_selectors_of_its_source(tmp_path: Path) -> None:
    bad = {"documents": [{**_CATALOG["documents"][1], "articles": []}]}  # type: ignore[dict-item]
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValidationError, match="celex and articles"):
        load_catalog(path)


class _FakeClient:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.requests_made = 0
        self.seen: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str] | None = None) -> RawResponse:
        self.requests_made += 1
        self.seen.append((url, headers or {}))
        for key, body in self.pages.items():
            if key in url:
                return RawResponse(status=200, url=url, body=body.encode())
        return RawResponse(status=404, url=url, body=b"")


def test_harvest_writes_markdown_images_and_one_manifest_per_jurisdiction(tmp_path: Path) -> None:
    client = _FakeClient(
        {
            "titles.json": '{"titles": [{"number": 12, "latest_issue_date": "2026-11-04"}]}',
            "section=217.132": _ECFR,
            "celex/02013R0575-20260626": _EU,
            "pra-rules/market-risk/01-01-2027": _PRA,
            "graphics/er24ja20.025.gif": "GIF89a",
        }
    )
    report = harvest_regulation(
        client,
        Catalog.model_validate(_CATALOG),
        documents_dir=tmp_path / "docs",
        root_dir="regulation",
        manifest_dir=tmp_path / "repo",
    )
    assert report.failed == {}
    assert [d.doc_key for d in report.converted] == ["uk-x", "eu-x", "eu-y", "us-x"]
    # The consolidated EU text is fetched once for both entries.
    assert sum("celex/" in url for url, _ in client.seen) == 1
    assert any("full/2026-11-04/title-12.xml?part=217&section=217.132" in u for u, _ in client.seen)
    assert dict(client.seen)[next(u for u, _ in client.seen if "celex" in u)]["Accept"] == (
        "application/xhtml+xml"
    )
    assert (tmp_path / "docs/regulation/eu/img/eu-x-001.jpg").is_file()
    assert (tmp_path / "docs/regulation/us/img/er24ja20.025.gif").read_bytes() == b"GIF89a"
    eu = yaml.safe_load((tmp_path / "repo/manifest-regulation-eu.yaml").read_text())
    assert eu["collection"] == "regulation" and eu["jurisdiction"] == "eu"
    assert [d["doc_key"] for d in eu["documents"]] == ["eu-x", "eu-y"]
    assert eu["documents"][0]["path"] == "regulation/eu/md/eu-x.md"
    uk = yaml.safe_load((tmp_path / "repo/manifest-regulation-uk.yaml").read_text())
    assert uk["documents"][0]["valid_from"] == "2027-01-01"
    assert uk["documents"][0]["source_url"].endswith("/pra-rules/market-risk/01-01-2027")


def test_formula_sidecars_replace_placeholders_and_mark_images_done(tmp_path: Path) -> None:
    from kbase.harvest.regulation import apply_image_formulas, latex_from_markdown, pending_images

    (tmp_path / "eu-x-001.jpg").write_bytes(b"x")
    (tmp_path / "eu-x-002.jpg").write_bytes(b"x")
    assert [p.name for p in pending_images(tmp_path)] == ["eu-x-001.jpg", "eu-x-002.jpg"]
    latex = latex_from_markdown("Some text\n\n$$\n\\mathsf { R W } _ { k } = 1 . 4\n$$\n")
    assert latex == "{RW}_{k}=1 . 4"
    (tmp_path / "eu-x-001.jpg.tex").write_text(latex + "\n")
    (tmp_path / "eu-x-002.jpg.tex").write_text("\n")  # MinerU found nothing
    assert pending_images(tmp_path) == []
    md = "with [formula: eu-x-001.jpg] and [formula: eu-x-002.jpg] here"
    text, placed, total = apply_image_formulas(md, tmp_path)
    assert text == "with ${RW}_{k}=1 . 4$ and [formula: eu-x-002.jpg] here"
    assert (placed, total) == (1, 2)


def test_cfr_chunks_carry_every_paragraph_id_including_heading_only_ones(tmp_path: Path) -> None:
    from kbase.ingestion.chunking import SectionChunker
    from kbase.schemas import ChunkPolicy

    path = tmp_path / "us.md"
    path.write_text(convert_ecfr(_ECFR, title="12 CFR 217.132").markdown, encoding="utf-8")
    parsed = MarkdownParser().parse(
        path, DocumentMeta(doc_key="us", title="us", doc_type="law", collection="regulation")
    )
    chunks = SectionChunker().chunk(
        parsed,
        ChunkPolicy(
            strategy="section", target_tokens=400, max_tokens=800, min_tokens=120, overlap_tokens=0
        ),
    )
    ids = [pid for c in chunks for pid in c.paragraph_ids]
    for expected in ("§ 217.132(a)", "§ 217.132(a)(1)", "§ 217.132(a)(1)(i)", "§ 217.132(b)"):
        assert expected in ids, expected
    assert any("§ 217.132(a) Methodologies." in c.content for c in chunks)
