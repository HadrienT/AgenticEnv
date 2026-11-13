"""legislation.gov.uk (UK) → the Markdown dialect `MarkdownParser` reads (WP21 wave 2).

The UK kept EU law in force at its exit as "assimilated law", revised on
legislation.gov.uk: the onshored CRR (until the PRA restates it), the EMIR margin and
prudent valuation standards. The site serves each document as CLML XML
(`<path>/data.xml`): divisions (`EUPart`, `EUTitle`, `EUChapter`, `EUSection`),
articles (`P1group` with its title, `P1` with its `Pnumber`), numbered paragraphs
(`P2`), points (`P3`), lists, tables, annexes (`Schedule`) and formulas in MathML.

Amendments are written inline (`Substitution`, `Addition`): the text kept is the text
in force. Commentaries, footnotes and alternative versions are left out. MathML becomes
LaTeX (`mathml_to_latex`), so formulas need no OCR.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup
from bs4.element import NavigableString, PageElement, Tag

from kbase.harvest.regulation_common import Conversion, Writer, article_selected, clean

_SKIP = frozenset(
    {
        "commentaryref",
        "footnoteref",
        "commentaries",
        "footnotes",
        "versions",
        "resources",
        "ukm:metadata",
        "image",
        "figure",
    }
)
_DIVISIONS = frozenset({"eupart", "eutitle", "euchapter", "eusection", "eusubsection"})

# ------------------------------------------------------------------------- MathML

_OPERATORS = {
    "∑": r"\sum",
    "∏": r"\prod",
    "∫": r"\int",
    "×": r"\times",
    "∙": r"\cdot",
    "·": r"\cdot",
    "⋅": r"\cdot",
    "−": "-",
    "≤": r"\leq",
    "≥": r"\geq",
    "≠": r"\neq",
    "≈": r"\approx",
    "∈": r"\in",
    "∞": r"\infty",
    "√": r"\sqrt",
    "∆": r"\Delta",
    "Δ": r"\Delta",
    "ρ": r"\rho",
    "σ": r"\sigma",
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\varepsilon",
    "θ": r"\theta",
    "λ": r"\lambda",
    "μ": r"\mu",
    "τ": r"\tau",
    "φ": r"\phi",
    "ω": r"\omega",
    "|": "|",
}


def _local(name: str) -> str:
    return name.lower().rsplit(":", 1)[-1]


def _symbol(text: str) -> str:
    text = text.strip()
    if text in _OPERATORS:
        return _OPERATORS[text]
    return "".join(_OPERATORS.get(ch, ch) for ch in text)


def mathml_to_latex(node: PageElement) -> str:
    """LaTeX for a MathML element (presentation markup, the subset legislation uses)."""
    if isinstance(node, NavigableString):
        return _symbol(str(node)) if str(node).strip() else ""
    if not isinstance(node, Tag):
        return ""
    name = _local(node.name)
    kids = [c for c in node.children if isinstance(c, Tag)]
    parts = [mathml_to_latex(c) for c in kids]

    def arg(i: int) -> str:
        return parts[i] if i < len(parts) else ""

    if name in {"mi", "mn", "mo"}:
        text = node.get_text()
        latex = _symbol(text)
        # A multi-letter identifier (`EAD`, `RW`) reads as one name, not a product.
        if name == "mi" and len(text.strip()) > 1 and text.strip().isalpha():
            return rf"\mathrm{{{text.strip()}}}"
        return latex
    if name == "mtext":
        text = clean(node.get_text())
        return rf"\text{{{text}}}" if text else ""
    if name in {"annotation", "annotation-xml", "mspace", "none", "mprescripts"}:
        return ""
    if name == "semantics":
        return arg(0)
    if name == "msub":
        return f"{{{arg(0)}}}_{{{arg(1)}}}"
    if name == "msup":
        return f"{{{arg(0)}}}^{{{arg(1)}}}"
    if name == "msubsup":
        return f"{{{arg(0)}}}_{{{arg(1)}}}^{{{arg(2)}}}"
    if name == "munder":
        return f"{arg(0)}_{{{arg(1)}}}"
    if name == "mover":
        return f"{arg(0)}^{{{arg(1)}}}"
    if name == "munderover":
        return f"{arg(0)}_{{{arg(1)}}}^{{{arg(2)}}}"
    if name == "mfrac":
        return rf"\frac{{{arg(0)}}}{{{arg(1)}}}"
    if name == "msqrt":
        return rf"\sqrt{{{''.join(parts)}}}"
    if name == "mroot":
        return rf"\sqrt[{arg(1)}]{{{arg(0)}}}"
    if name == "mfenced":
        opening = str(node.get("open", "("))
        closing = str(node.get("close", ")"))
        separator = str(node.get("separators", ",")).strip()[:1] or ","
        inner = separator.join(parts)
        return rf"\left{_fence(opening)}{inner}\right{_fence(closing)}"
    if name == "mtable":
        rows = [
            " & ".join(mathml_to_latex(cell) for cell in row.find_all(_is_cell, recursive=False))
            for row in node.find_all(_is_row, recursive=False)
        ]
        return r"\begin{matrix}" + r" \\ ".join(rows) + r"\end{matrix}"
    return (
        " ".join(p for p in parts if p)
        if name not in {"math", "mrow", "mstyle"}
        else "".join(parts)
    )


def _fence(char: str) -> str:
    return {"{": r"\{", "}": r"\}", "": ".", "|": "|"}.get(char, char)


def _is_row(tag: Tag) -> bool:
    return _local(tag.name) in {"mtr", "mlabeledtr"}


def _is_cell(tag: Tag) -> bool:
    return _local(tag.name) == "mtd"


# --------------------------------------------------------------------------- CLML


class _Converter:
    def __init__(self, title: str, articles: list[str] | None) -> None:
        self.out = Writer(title)
        self.articles = articles
        self.article = ""

    def inline(self, node: PageElement) -> str:
        if isinstance(node, NavigableString):
            return str(node)
        if not isinstance(node, Tag):
            return ""
        name = node.name.lower()
        if name in _SKIP:
            return ""
        if _local(name) == "math":
            latex = re.sub(r"\s+", " ", mathml_to_latex(node)).strip()
            if not latex:
                return ""
            self.out.formulas += 1
            return f" ${latex}$ "
        if name == "inferior":
            return f"_{{{clean(self.inline_children(node))}}}"
        if name == "superior":
            return f"^{{{clean(self.inline_children(node))}}}"
        return self.inline_children(node)

    def inline_children(self, node: Tag) -> str:
        return "".join(self.inline(c) for c in node.children)

    def table(self, node: Tag) -> None:
        rows: list[list[str]] = []
        for tr in node.find_all("tr"):
            if not isinstance(tr, Tag):
                continue
            cells: list[str] = []
            for cell in tr.find_all(["td", "th"], recursive=False):
                if not isinstance(cell, Tag):
                    continue
                cells.append(clean(self.inline(cell)))
                span = str(cell.get("colspan") or "1")
                if span.isdigit() and int(span) > 1:
                    cells.extend([""] * (int(span) - 1))
            rows.append(cells)
        caption = node.find("ctitle")
        if isinstance(caption, Tag):
            self.out.text(self.inline(caption))
        self.out.table(rows)

    def number(self, node: Tag) -> str:
        pnumber = node.find("pnumber", recursive=False)
        return clean(self.inline(pnumber)) if isinstance(pnumber, Tag) else ""

    def block(self, node: Tag, label: str = "") -> None:
        """Paragraph-level content in order; `label` prefixes the first text line
        (`(a)` of a point, `(1)` of a list item)."""
        pending = label
        for child in node.children:
            if isinstance(child, NavigableString):
                continue
            if not isinstance(child, Tag):
                continue
            name = child.name.lower()
            if name in _SKIP or name == "pnumber":
                continue
            if name == "tabular":
                self.table(child)
            elif name == "text":
                text = clean(self.inline(child))
                if text:
                    self.out.text(f"{pending} {text}".strip())
                    pending = ""
            elif name in {"p3", "p4", "p5"}:
                self.block(child, f"({self.number(child).strip('()')})")
            elif name == "keylistitem":
                # A definition after "where:": `<Key>h</Key>` then its meaning.
                key = child.find("key", recursive=False)
                symbol = clean(self.inline(key)) if isinstance(key, Tag) else ""
                meaning = clean(
                    " ".join(
                        self.inline(c)
                        for c in child.children
                        if isinstance(c, Tag) and c is not key
                    )
                )
                self.out.text(f"{symbol} = {meaning}" if symbol else meaning)
            elif name == "listitem":
                override = str(child.get("numberoverride") or "")
                self.block(child, override)
            elif name == "p2" and self.article:
                par = self.number(child).rstrip(".")
                if re.fullmatch(r"\d{1,3}[a-z]?", par):
                    self.out.paragraph(f"Article {self.article}({par})")
                self.block(child)
            else:
                if pending and not child.find(["text"]):
                    self.out.text(pending)
                    pending = ""
                self.block(child, pending)
                pending = ""

    def walk(self, node: Tag) -> None:
        for child in node.children:
            if not isinstance(child, Tag):
                continue
            name = child.name.lower()
            if name in _SKIP:
                continue
            if name in _DIVISIONS:
                number = child.find("number", recursive=False)
                title = child.find("ctitle", recursive=False)
                heading = " ".join(
                    clean(self.inline(el)) for el in (number, title) if isinstance(el, Tag)
                )
                if heading and self._division_has_selected(child):
                    self.out.heading(2, heading)
                self.walk(child)
            elif name == "p1group":
                title = child.find("ctitle", recursive=False)
                for p1 in child.find_all("p1", recursive=False):
                    if isinstance(p1, Tag):
                        self.article_p1(
                            p1, clean(self.inline(title)) if isinstance(title, Tag) else ""
                        )
            elif name == "p1":
                self.article_p1(child, "")
            elif name == "schedule":
                if self.articles is not None:
                    continue
                number = child.find("number", recursive=False)
                title = child.find("ctitle")
                heading = " ".join(
                    clean(self.inline(el)) for el in (number, title) if isinstance(el, Tag)
                )
                self.out.heading(2, heading or "Annex")
                self.article = ""
                body = child.find("schedulebody")
                if isinstance(body, Tag):
                    self.block(body)
            else:
                self.walk(child)

    def _division_has_selected(self, division: Tag) -> bool:
        if self.articles is None:
            return True
        return any(
            article_selected(n, self.articles)
            for n in (self._article_number(p1) for p1 in division.find_all("p1"))
            if n
        )

    def _article_number(self, p1: Tag) -> str:
        m = re.match(r"Article\s+(\d{1,4}[a-z]*)", self.number(p1))
        return m.group(1) if m else ""

    def article_p1(self, p1: Tag, title: str) -> None:
        number = self._article_number(p1)
        if not number:
            return
        if self.articles is not None and not article_selected(number, self.articles):
            return
        self.article = number
        self.out.blocks.append(f"### Article {number} {title}".strip())
        self.out.paragraphs += 1
        self.block(p1)


_TITLE_TAG_RE = re.compile(r"<(/?)Title\b")


def convert_legislation(xml: str, *, title: str, articles: list[str] | None) -> Conversion:
    """A CLML document: the articles in `articles` (ranges, as for the EU), or every
    article and annex when `articles` is None."""
    # `html.parser` reads `<Title>` as an HTML page title (raw text, markup kept): renamed.
    soup = BeautifulSoup(_TITLE_TAG_RE.sub(r"<\1ctitle", xml), "html.parser")
    body = soup.find(["eubody", "body"])
    if not isinstance(body, Tag):
        raise ValueError("no EUBody/Body in the legislation.gov.uk document")
    conv = _Converter(title, articles)
    conv.walk(body)
    schedules = soup.find("schedules")
    if isinstance(schedules, Tag) and articles is None:
        conv.walk(schedules)
    if conv.out.paragraphs == 0:
        raise ValueError(f"no article of {articles} found")
    return conv.out.result()
