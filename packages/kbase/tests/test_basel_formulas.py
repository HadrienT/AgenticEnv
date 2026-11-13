# ruff: noqa: E501
from __future__ import annotations

from kbase.harvest.basel import chapter_pdf_url
from kbase.harvest.basel_formulas import clean_latex, merge_formulas

_HTML_MD = """# MAR21 Sensitivities

#### MAR21.4

(3) The weighted sensitivity is the product of the net sensitivity and the risk weight as defined in MAR21.39. [formula: MAR21_1.svg]

(4) Within bucket aggregation uses the prescribed correlation set out in the following formula, where the square root is floored at zero: [formula: MAR21_3.svg]

#### MAR21.5

No formula here.

#### MAR21.6

Under the medium scenario the correlation [formula: a.svg] is kept, and in the high scenario [formula: b.svg] is multiplied.

#### MAR21.7

Aggregation as in [formula: c.svg] for each class.
"""

_PDF_MD = """## 21.4

3. The weighted sensitivity is the product of the net sensitivityand the risk weight as defined in MAR21.39 $W S _ { k } = R W _ { k } s _ { k }$

4. Within bucket aggregation uses the prescribed correlation set out in the following formula, where the square root is floored at zero:
$$
K _ { b } = \\sqrt { \\mathsf { m a x } ( 0 , x ) }
$$

## 21.6

Under the medium scenario the correlation $\\rho$ is kept, and in the high scenario $\\gamma$ is multiplied.

## 21.7

Something unrelated entirely $Z$ and more words
"""


def test_formulas_go_where_their_context_matches() -> None:
    merged, stats = merge_formulas(_HTML_MD, _PDF_MD)
    assert "MAR21.39. $WS_{k}=RW_{k}s_{k}$" in merged
    assert "floored at zero: $K_{b}=\\sqrt{{max}(0,x)}$" in merged
    assert "correlation $\\rho$ is kept" in merged and "scenario $\\gamma$ is" in merged
    assert stats.placeholders == 5 and stats.placed == 4


def test_an_unconvincing_match_keeps_the_placeholder_and_lists_the_formula() -> None:
    merged, stats = merge_formulas(_HTML_MD, _PDF_MD)
    tail = merged[merged.index("#### MAR21.7") :]
    assert "[formula: c.svg]" in tail  # no shared word: not placed, even by order
    assert "Formulas of this paragraph (from the PDF): $Z$" in tail
    assert stats.listed == 1


def test_paragraph_missing_from_the_pdf_is_reported() -> None:
    _, stats = merge_formulas(_HTML_MD, "## 21.4\n\nnothing\n")
    assert "MAR21.6" in stats.paragraphs_without_pdf


def testclean_latex_drops_fonts_and_spelled_out_words() -> None:
    assert clean_latex("\\mathsf { m a x } ( 0 , W S _ { k } )") == "{max}(0,WS_{k})"


def test_chapter_pdf_url_prefers_the_pdf_without_footnotes() -> None:
    html = (
        '<a href="/committees/bcbs/basel-framework/81340/chapter.pdf">PDF</a>'
        '<a href="/committees/bcbs/basel-framework/81340/chapter-no-footnotes.pdf">PDF</a>'
    )
    assert chapter_pdf_url(html) == (
        "https://www.bis.org/committees/bcbs/basel-framework/81340/chapter-no-footnotes.pdf"
    )
    assert chapter_pdf_url("<html></html>") is None
