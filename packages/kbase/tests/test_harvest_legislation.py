# ruff: noqa: E501  (XML and HTML fixtures copied from the sources)
"""WP21 wave 2: legislation.gov.uk (CLML, MathML), Federal Register proposals, PDFs."""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from corelib.errors import DependencyError
from kbase.harvest.http import RawResponse
from kbase.harvest.legislation import convert_legislation, mathml_to_latex
from kbase.harvest.regulation import Catalog, convert_fr, harvest_regulation
from kbase.regulatory import paragraph_id

_CLML = """<Legislation xmlns="http://www.legislation.gov.uk/namespaces/legislation">
<ukm:Metadata><dc:title>ignored</dc:title></ukm:Metadata>
<EURetained><EUBody>
<EUPart><Number>PART THREE</Number><Title>CAPITAL REQUIREMENTS</Title>
<EUTitle><Number>TITLE VI</Number><Title>OWN FUNDS REQUIREMENTS FOR CVA RISK</Title>
<P1group><Title><Substitution ChangeId="x">Meaning of CVA</Substitution></Title>
<P1 id="article-381"><Pnumber>Article 381</Pnumber><P1para><Text>Credit valuation adjustment means an adjustment<FootnoteRef Ref="f1"/>.</Text></P1para></P1></P1group>
<P1group><Title>Standardised method</Title>
<P1 id="article-384"><Pnumber><Substitution>Article 384</Substitution></Pnumber><P1para>
<P2 id="article-384-1"><Pnumber>1</Pnumber><P2para><Text>An institution shall calculate:</Text></P2para>
<P2para><Text><math xmlns="http://www.w3.org/1998/Math/MathML"><mrow><mi>K</mi></mrow><mo>=</mo><mi>2.33</mi><mo>×</mo><msqrt><mi>h</mi></msqrt><mo>×</mo><msubsup><mi>EAD</mi><mi>i</mi><mi>total</mi></msubsup></math></Text></P2para>
<P2para><Text>where:</Text></P2para>
<KeyList><KeyListItem><Key><math xmlns="http://www.w3.org/1998/Math/MathML"><mi>h</mi></math></Key><ListItem><Para><Text>the one-year risk horizon;</Text></Para></ListItem></KeyListItem></KeyList>
<P3><Pnumber>a</Pnumber><P3para><Text>first point;</Text></P3para></P3>
</P2>
<P2 id="article-384-2"><Pnumber>2</Pnumber><P2para><Text>Second paragraph.</Text></P2para></P2>
</P1para></P1></P1group>
<P1group><Title>Out of range</Title><P1 id="article-390"><Pnumber>Article 390</Pnumber><P1para><Text>No.</Text></P1para></P1></P1group>
</EUTitle></EUPart>
</EUBody>
<Schedules><Schedule><Number>ANNEX I</Number><TitleBlock><Title>Haircuts</Title></TitleBlock><ScheduleBody><P><Tabular><Title>Table 1</Title><table><tbody><tr><th>Step</th><th>PD</th></tr><tr><td>1</td><td>0,10 %</td></tr></tbody></table></Tabular></P></ScheduleBody></Schedule></Schedules>
</EURetained><Commentaries><Commentary id="c1"><Para><Text>Substituted by ...</Text></Para></Commentary></Commentaries>
</Legislation>"""


def test_mathml_becomes_latex() -> None:
    soup = BeautifulSoup(
        "<math><mfrac><mn>1</mn><mrow><mi>e</mi><mo>−</mo><mn>0.05</mn></mrow></mfrac>"
        "<munderover><mo>∑</mo><mi>i</mi><mi>n</mi></munderover>"
        '<mfenced open="(" close=")"><mi>a</mi><mi>b</mi></mfenced></math>',
        "html.parser",
    )
    assert mathml_to_latex(soup.find("math")) == r"\frac{1}{e-0.05}\sum_{i}^{n}\left(a,b\right)"


def test_clml_articles_paragraphs_definitions_and_formulas() -> None:
    conv = convert_legislation(_CLML, title="UK CRR CVA", articles=["381-386"])
    md = conv.markdown
    ids = [
        paragraph_id(line.lstrip("#").strip()) for line in md.splitlines() if line.startswith("###")
    ]
    assert ids == ["Article 381", "Article 384", "Article 384(1)", "Article 384(2)"]
    assert "### Article 381 Meaning of CVA" in md and "Substitution" not in md
    assert "## PART THREE CAPITAL REQUIREMENTS" in md
    assert r"$K=2.33\times\sqrt{h}\times{\mathrm{EAD}}_{i}^{\mathrm{total}}$" in md
    assert "$h$ = the one-year risk horizon;" in md
    assert "(a) first point;" in md
    assert "Article 390" not in md and "Substituted by" not in md and "Haircuts" not in md
    assert conv.formulas == 2


def test_clml_without_a_selection_keeps_every_article_and_the_annexes() -> None:
    md = convert_legislation(_CLML, title="UK", articles=None).markdown
    assert "### Article 390 Out of range" in md
    assert "## ANNEX I Haircuts" in md and "| Step | PD |" in md


_FR = """<html><body>
<h2>V. Discussion</h2><p>(a) Preamble text, not rule text.</p>
<h2>Text of Common Rule</h2>
<h3>Subpart E&mdash;Expanded Risk-Based Approach</h3>
<h4>&sect;&thinsp;__.114&emsp;Derivative Contracts</h4><p>(a) E text.</p>
<h2>Table 1 to &sect;&thinsp;__.114&mdash;Factors</h2>
<h3>Subpart F&mdash;Market Risk and CVA</h3>
<h4>&sect;&thinsp;__.222&emsp;Basic CVA Approach</h4>
<p>(a) <em>Basic CVA approach capital requirement</em>. It equals K<sub>basic</sub>:<span class="printed-page" data-page="15253">(printed page 15253)</span></p>
<p><img src="https://img.federalregister.gov/EP27MR26.342/EP27MR26.342_original_size.png"></p>
<p>(1) The parameter, &beta;, equals 0.25;</p>
<h1>List of Subjects</h1><p>(b) not rule text</p>
</body></html>"""


def test_federal_register_subpart_of_the_common_rule() -> None:
    conv = convert_fr(_FR, title="US proposal F", part="217", subpart="F")
    md = conv.markdown
    ids = [
        paragraph_id(line.lstrip("#").strip())
        for line in md.splitlines()
        if line.startswith("####")
    ]
    assert ids == ["§ 217.222", "§ 217.222(a)", "§ 217.222(a)(1)"]
    assert "#### § 217.222(a) Basic CVA approach capital requirement" not in md  # text follows
    assert "K_{basic}" in md and "printed page" not in md
    assert "E text" not in md and "Preamble" not in md and "not rule text" not in md
    assert conv.image_urls == {
        "ep27mr26.342.png": "https://img.federalregister.gov/EP27MR26.342/EP27MR26.342_original_size.png"
    }
    e = convert_fr(_FR, title="US proposal E", part="217", subpart="E").markdown
    assert "#### § 217.114 Derivative Contracts" in e and "Basic CVA" not in e


class _Client:
    def __init__(self, pages: dict[str, bytes]) -> None:
        self.pages = pages
        self.requests_made = 0

    def get(self, url: str, headers: dict[str, str] | None = None) -> RawResponse:
        self.requests_made += 1
        for key, body in self.pages.items():
            if key in url:
                return RawResponse(status=200, url=url, body=body)
        return RawResponse(status=404, url=url, body=b"")


def _catalog(**entry: object) -> Catalog:
    base = {"jurisdiction": "uk", "title": "T", "authors": ["A"], "topic": "reg-x", "license": "l"}
    return Catalog.model_validate({"documents": [{**base, **entry}]})


def test_pdf_source_keeps_the_pdf_and_points_the_manifest_at_it(tmp_path: Path) -> None:
    import yaml

    client = _Client({"cp926app2.pdf": b"%PDF-1.6 body"})
    report = harvest_regulation(
        client,
        _catalog(doc_key="uk-cp", source="pdf", doc_type="proposal", url="https://x/cp926app2.pdf"),
        documents_dir=tmp_path / "docs",
        root_dir="regulation",
        manifest_dir=tmp_path / "repo",
    )
    assert report.failed == {}
    assert (tmp_path / "docs/regulation/uk/raw/uk-cp.pdf").read_bytes().startswith(b"%PDF")
    entry = yaml.safe_load((tmp_path / "repo/manifest-regulation-uk.yaml").read_text())[
        "documents"
    ][0]
    assert entry["path"] == "regulation/uk/raw/uk-cp.pdf" and entry["doc_type"] == "proposal"


def test_pdf_source_refuses_a_page(tmp_path: Path) -> None:
    client = _Client({"d475.pdf": b"<!DOCTYPE html><title>Margin</title>"})
    report = harvest_regulation(
        client,
        _catalog(doc_key="x", source="pdf", url="https://x/d475.pdf"),
        documents_dir=tmp_path,
        root_dir="regulation",
        manifest_dir=tmp_path,
    )
    assert "did not return a PDF" in report.failed["x"]


def test_leg_source_fetches_the_data_xml(tmp_path: Path) -> None:
    client = _Client({"eur/2013/575/part/THREE/title/VI/data.xml": _CLML.encode()})
    report = harvest_regulation(
        client,
        _catalog(
            doc_key="uk-crr-cva",
            source="leg",
            leg_path="eur/2013/575/part/THREE/title/VI",
            articles=["381-386"],
        ),
        documents_dir=tmp_path / "docs",
        root_dir="regulation",
        manifest_dir=tmp_path / "repo",
    )
    assert report.failed == {} and report.converted[0].paragraphs == 4


def test_catalogue_selectors_of_the_new_sources() -> None:
    with pytest.raises(ValueError, match="leg needs leg_path"):
        _catalog(doc_key="x", source="leg")
    with pytest.raises(ValueError, match="fr needs url, part and subpart"):
        _catalog(doc_key="x", source="fr", url="u")
    assert DependencyError  # imported for the harvest failures above
