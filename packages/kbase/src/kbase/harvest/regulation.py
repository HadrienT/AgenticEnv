"""Binding rules of the EU, the UK and the US → the Markdown dialect `MarkdownParser`
reads (WP21 §5).

Three sources, one converter each; every numbered paragraph becomes its own heading so
its chunks carry the id (`kbase.regulatory.paragraph_id`):

- **eCFR** (US): the versioner API's XML, one `DIV8` per section. Paragraphs carry their
  CFR markers, `(a)`, `(1)`, `(i)`, `(A)`, then italic `(1)` and `(i)`, read into a path:
  `#### § 217.132(c)(5)`.
- **Cellar** (EU): the Publications Office's consolidated XHTML of a regulation (EUR-Lex
  itself challenges scripts). Articles of the selected ranges become `### Article 274
  Exposure value`, their numbered paragraphs `#### Article 274(2)`. Formulas are JPEG
  images: saved next to the Markdown and replaced by `[formula: <file>]`, never guessed.
- **PRA Rulebook** (UK): a rule part as it applies on a given date. CRR-style articles
  become `### Article 325c ...` with `#### Article 325c(2)`; other numbered rules
  `#### Rule 2.1`.

A catalogue (`configs/harvest/regulation-*.yaml`) lists the documents to build: source,
what to keep, and the metadata of their manifest entry.
"""

from __future__ import annotations

import base64
import re
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal, Protocol

import yaml
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from bs4.element import NavigableString, PageElement, Tag
from corelib.errors import AppError, DependencyError, ValidationError
from pydantic import BaseModel, model_validator

from kbase.harvest.basel_formulas import clean_latex
from kbase.harvest.http import RawResponse
from kbase.schemas import Jurisdiction

ECFR_ROOT = "https://www.ecfr.gov"
CELLAR_ROOT = "http://publications.europa.eu/resource/celex"
PRA_ROOT = "https://www.prarulebook.co.uk"

_WS_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def _escape(line: str) -> str:
    """A line starting with these would be re-read as structure by `MarkdownParser`."""
    return "\\" + line if line.startswith(("#", "$$", "|", "<!--")) else line


def _classes(el: Tag) -> set[str]:
    value = el.get("class")
    if isinstance(value, str):
        return set(value.split())
    return set(value or [])


def _pipe_table(rows: list[list[str]]) -> str | None:
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        return None
    width = max(len(r) for r in rows)
    padded = [[c.replace("|", "\\|") for c in r] + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(padded[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in padded[1:]]
    return "\n".join(lines)


def _table_rows(table: Tag, inline: Callable[[PageElement], str]) -> list[list[str]]:
    """Cell texts row by row; a cell spanning n columns is followed by n-1 empty ones so
    the columns of the header and the body line up."""
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        if not isinstance(tr, Tag):
            continue
        cells: list[str] = []
        for cell in tr.find_all(["td", "th"], recursive=False):
            if not isinstance(cell, Tag):
                continue
            cells.append(_clean(inline(cell)))
            span = str(cell.get("colspan") or "1")
            if span.isdigit() and int(span) > 1:
                cells.extend([""] * (int(span) - 1))
        rows.append(cells)
    return rows


@dataclass
class Conversion:
    markdown: str
    paragraphs: int = 0
    tables: int = 0
    formulas: int = 0
    # Formula images to write next to the Markdown: file name -> bytes.
    images: dict[str, bytes] = field(default_factory=dict)
    # Formula images to download next to the Markdown: file name -> URL (eCFR graphics).
    image_urls: dict[str, str] = field(default_factory=dict)


class _Writer:
    """Accumulates Markdown blocks separated by blank lines."""

    def __init__(self, title: str) -> None:
        self.blocks: list[str] = [f"# {title}"]
        self.paragraphs = 0
        self.tables = 0
        self.formulas = 0
        self.images: dict[str, bytes] = {}

    def heading(self, level: int, text: str) -> None:
        self.blocks.append(f"{'#' * level} {_clean(text)}")

    def paragraph(self, pid: str, title: str = "") -> None:
        self.paragraphs += 1
        self.heading(4, f"{pid} {title}".strip())

    def text(self, text: str) -> None:
        cleaned = _clean(text)
        if cleaned:
            self.blocks.append(_escape(cleaned))

    def equation(self, latex: str) -> None:
        self.formulas += 1
        self.blocks.append(f"$$\n{latex.strip()}\n$$")

    def table(self, rows: list[list[str]]) -> None:
        md = _pipe_table(rows)
        if md is not None:
            self.tables += 1
            self.blocks.append(md)
            return
        # One row is layout, not a table: `RC | = | the replacement cost ...`.
        for row in rows:
            self.text(" ".join(c for c in row if c.strip()))

    def result(self) -> Conversion:
        return Conversion(
            markdown="\n\n".join(self.blocks) + "\n",
            paragraphs=self.paragraphs,
            tables=self.tables,
            formulas=self.formulas,
            images=self.images,
        )


# --------------------------------------------------------------------------- eCFR (US)

_ROMAN_RE = re.compile(r"^(?=[ivxl]+$)l?x{0,3}(ix|iv|v?i{0,3})$")
# `(a)`, `(1)`, `(i)`, `(A)`; italic markers are wrapped in \x01 … \x02 by `_ecfr_inline`.
_MARKER_RE = re.compile(r"^\((\x01?)([0-9]{1,3}|[a-z]{1,5}|[A-Z]{1,3})(\x02?)\)\s*")
_ITALIC_HEAD_RE = re.compile(r"^\x01([^\x01\x02]{1,200})\x02[\s.—–-]*")


def _to_roman(n: int) -> str:
    out = ""
    for value, symbol in ((10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        while n >= value:
            out += symbol
            n -= value
    return out


def _from_roman(s: str) -> int:
    values = {"i": 1, "v": 5, "x": 10, "l": 50}
    total = 0
    for i, ch in enumerate(s):
        v = values[ch]
        total += -v if i + 1 < len(s) and values[s[i + 1]] > v else v
    return total


class _CfrPath:
    """The paragraph path `(c)(5)(ii)`: levels 1 `(a)`, 2 `(1)`, 3 `(i)`, 4 `(A)`,
    5 italic `(1)`, 6 italic `(i)`. A lower-case roman numeral is ambiguous (`(i)` is
    also the letter after `(h)`): it is the expected next roman numeral when a level-2
    paragraph is open, else the expected next letter."""

    def __init__(self) -> None:
        self.path: list[tuple[int, str]] = []

    def _label_at(self, level: int) -> str | None:
        return next((label for lvl, label in self.path if lvl == level), None)

    def _level(self, label: str, italic: bool) -> int:
        if italic:
            return 5 if label.isdigit() else 6
        if label.isdigit():
            return 2
        if label.isupper():
            return 4
        if not _ROMAN_RE.match(label):
            return 1
        depth = max((lvl for lvl, _ in self.path), default=0)
        current_roman = self._label_at(3)
        roman_next = _to_roman(_from_roman(current_roman) + 1) if current_roman else "i"
        current_letter = self._label_at(1)
        letter_next = chr(ord(current_letter[-1]) + 1) if current_letter else "a"
        if depth >= 2 and label == roman_next:
            return 3
        if label == letter_next:
            return 1
        return 3 if depth >= 2 else 1

    def push(self, label: str, italic: bool) -> str:
        level = self._level(label, italic)
        self.path = [(lvl, lab) for lvl, lab in self.path if lvl < level] + [(level, label)]
        return "".join(f"({lab})" for _, lab in self.path)


def _ecfr_inline(node: PageElement) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""
    name = node.name.lower()
    inner = "".join(_ecfr_inline(c) for c in node.children)
    if name == "i":
        return f"\x01{inner}\x02"
    if name == "e":
        kind = str(node.get("t") or node.get("T") or "")
        if kind == "52":
            return f"_{{{_clean(inner)}}}"
        if kind == "51":
            return f"^{{{_clean(inner)}}}"
        return inner
    if name in {"su", "sup"}:
        return f"^{{{_clean(inner)}}}"
    if name == "img":
        # `/graphics/er24ja20.025.gif`: a Federal Register graphic, unique by name.
        src = str(node.get("src") or "")
        graphic = src.rsplit("/", 1)[-1]
        return f" [formula: {graphic}] " if _GRAPHIC_RE.fullmatch(graphic) else "[formula: image]"
    return inner


_GRAPHIC_RE = re.compile(r"[A-Za-z0-9_.-]{1,80}\.(?:gif|png|jpg)")


def _plain(text: str) -> str:
    return text.replace("\x01", "").replace("\x02", "")


def _ecfr_table(out: _Writer, table: Tag) -> None:
    caption = table.find("caption")
    if isinstance(caption, Tag):
        out.text(_plain(_ecfr_inline(caption)))
    out.table(_table_rows(table, lambda node: _plain(_ecfr_inline(node))))


def _ecfr_paragraph(out: _Writer, p: Tag, number: str, path: _CfrPath) -> None:
    """A `<P>`: its leading markers set the paragraph path; `(a) Heading—(1) text`
    gives (a) its heading and the text to (a)(1)."""
    text = _ecfr_inline(p)
    out.formulas += text.count("[formula:")
    pid = ""
    stripped = text.lstrip()
    while True:
        m = _MARKER_RE.match(stripped)
        if m is None:
            break
        pid = path.push(m.group(2), italic=bool(m.group(1)))
        stripped = stripped[m.end() :]
        head_m = _ITALIC_HEAD_RE.match(stripped)
        if head_m is not None and _MARKER_RE.match(stripped[head_m.end() :]):
            out.paragraph(f"§ {number}{pid}", _plain(head_m.group(1)))
            stripped = stripped[head_m.end() :]
            pid = ""
    if pid:
        out.paragraph(f"§ {number}{pid}")
    out.text(_plain(stripped))


_ECFR_SKIP = frozenset({"head", "cita", "auth", "source", "secauth", "ednote"})


def _ecfr_walk(out: _Writer, node: Tag, number: str, path: _CfrPath, quoted: bool) -> None:
    for child in node.children:
        if not isinstance(child, Tag):
            continue
        name = child.name.lower()
        if name in _ECFR_SKIP:
            continue
        if name in {"table", "gpotable"}:
            _ecfr_table(out, child)
        elif name in {"img", "gph", "math"}:
            out.formulas += 1
            out.text("[formula: image]")
        elif name == "p" and not quoted:
            _ecfr_paragraph(out, child, number, path)
        elif name in {"p", "fp", "fp-1", "fp-2", "ftnt"}:
            text = _ecfr_inline(child)
            out.formulas += text.count("[formula:")
            out.text(_plain(text))
        else:
            # Containers (DIV, EXTRACT): an EXTRACT quotes text, its markers are not ours.
            _ecfr_walk(out, child, number, path, quoted or name == "extract")


def convert_ecfr(xml: str, *, title: str) -> Conversion:
    """One or several CFR sections (`DIV8`) of the versioner API's XML."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(xml, "html.parser")
    out = _Writer(title)
    sections = [s for s in soup.find_all("div8") if isinstance(s, Tag)]
    if not sections:
        raise ValueError("no CFR section (DIV8) in the response")
    for section in sections:
        number = str(section.get("n") or "")
        head = section.find("head")
        heading = _clean(head.get_text(" ")) if isinstance(head, Tag) else f"§ {number}"
        out.paragraph(f"§ {number}", heading.removeprefix(f"§ {number}").strip())
        _ecfr_walk(out, section, number, _CfrPath(), quoted=False)
    result = out.result()
    result.image_urls = {
        name: f"{ECFR_ROOT}/graphics/{name}"
        for name in _IMAGE_PLACEHOLDER_RE.findall(result.markdown)
    }
    return result


# ------------------------------------------------------------------------ Cellar (EU)

_ARTICLE_ID_RE = re.compile(r"^art_(\d{1,4})([a-z]*)$")
_ARTICLE_NUM_RE = re.compile(r"^(\d{1,4})([a-z]*)$")
_AMENDMENT_MARKER_RE = re.compile(r"[▼►◄]\s*[A-Z]\d*")


def _article_key(number: str) -> tuple[int, int, str]:
    m = _ARTICLE_NUM_RE.match(number)
    if m is None:
        raise ValueError(f"not an article number: {number}")
    return int(m.group(1)), len(m.group(2)), m.group(2)


def article_selected(number: str, ranges: list[str]) -> bool:
    """`ranges`: `"271-311"`, `"325-325bp"`, `"105"`; letters order `325 < 325a < 325z
    < 325aa`, as the CRR numbers inserted articles."""
    key = _article_key(number)
    for spec in ranges:
        low, _, high = spec.partition("-")
        if _article_key(low.strip()) <= key <= _article_key((high or low).strip()):
            return True
    return False


class _EuConverter:
    def __init__(self, title: str, doc_key: str) -> None:
        self.out = _Writer(title)
        self.doc_key = doc_key
        self.article = ""

    def inline(self, node: PageElement) -> str:
        if isinstance(node, NavigableString):
            return _AMENDMENT_MARKER_RE.sub("", str(node))
        if not isinstance(node, Tag):
            return ""
        classes = _classes(node)
        if classes & {"modref", "arrow"} or node.name == "a" and "footnote" in classes:
            return ""
        if node.name == "img":
            return self.image(node)
        inner = "".join(self.inline(c) for c in node.children)
        if "subscript" in classes or node.name == "sub":
            return f"_{{{_clean(inner)}}}" if _clean(inner) else ""
        if "superscript" in classes or node.name == "sup":
            return f"^{{{_clean(inner)}}}" if _clean(inner) else ""
        return inner

    def image(self, img: Tag) -> str:
        src = str(img.get("src") or "")
        if not src.startswith("data:image/"):
            return "[formula: image]"
        header, _, payload = src.partition(",")
        ext = "png" if "png" in header else "jpg"
        name = f"{self.doc_key}-{len(self.out.images) + 1:03d}.{ext}"
        try:
            self.out.images[name] = base64.b64decode(payload)
        except ValueError:
            return "[formula: image]"
        self.out.formulas += 1
        return f" [formula: {name}] "

    def block(self, node: Tag) -> None:
        """Paragraph-level content of an article, in order."""
        for child in node.children:
            self.node(child)

    def node(self, child: PageElement) -> None:
        if isinstance(child, NavigableString):
            self.out.text(self.inline(child))
            return
        if not isinstance(child, Tag):
            return
        classes = _classes(child)
        if classes & {"modref", "arrow"}:
            return
        if child.name == "table":
            self.table(child)
        elif "grid-container" in classes:
            self.list_item(child)
        elif child.name == "p" or not child.find(["p", "div", "table"], recursive=False):
            self.out.text(self.inline(child))
        else:
            self.block(child)

    def list_item(self, item: Tag) -> None:
        """`(a)` | text, where the text may hold a nested list."""
        label_el = item.find(class_="grid-list-column-1")
        body_el = item.find(class_="grid-list-column-2")
        label = _clean(self.inline(label_el)) if isinstance(label_el, Tag) else ""
        if not isinstance(body_el, Tag):
            self.out.text(label)
            return
        first = True
        for part in body_el.children:
            if isinstance(part, Tag) and (
                "grid-container" in _classes(part) or part.name == "table"
            ):
                self.node(part)
                continue
            text = _clean(self.inline(part))
            if text:
                self.out.text(f"{label} {text}" if first else text)
                first = False
        if first and label:
            self.out.text(label)

    def table(self, table: Tag) -> None:
        rows = _table_rows(table, self.inline)
        # Old consolidations lay lists out as two-column tables: `(a)` | text.
        if rows and all(len(r) == 2 and re.fullmatch(r"\(?[0-9a-z]{1,5}[.)]", r[0]) for r in rows):
            for label, text in rows:
                self.out.text(f"{label} {text}")
            return
        self.out.table(rows)

    def article_body(self, div: Tag, number: str) -> None:
        for child in div.children:
            if not isinstance(child, Tag):
                continue
            classes = _classes(child)
            if classes & {"title-article-norm", "eli-title", "modref", "arrow"}:
                continue
            numbered = child.find(class_="no-parag", recursive=False)
            if "norm" in classes and isinstance(numbered, Tag):
                par = _clean(numbered.get_text()).rstrip(".")
                if re.fullmatch(r"\d{1,3}[a-z]?", par):
                    self.out.paragraph(f"Article {number}({par})")
                    numbered.extract()
                    self.block(child)
                    continue
            if child.name == "table":
                self.table(child)
            elif child.name == "p":
                self.out.text(self.inline(child))
            else:
                self.block(child)


def convert_eu(xhtml: str, *, title: str, doc_key: str, articles: list[str]) -> Conversion:
    """The articles of `articles` (ranges) from a consolidated regulation, with the
    division titles (Part, Title, Chapter, Section) that precede them."""
    soup = BeautifulSoup(xhtml, "html.parser")
    conv = _EuConverter(title, doc_key)
    pending_division: list[str] = []
    found = 0
    for el in soup.find_all(["p", "div"]):
        if not isinstance(el, Tag):
            continue
        classes = _classes(el)
        if el.name == "p" and classes & {"title-division-1", "title-division-2"}:
            if "title-division-1" in classes:
                pending_division = []
            pending_division.append(_clean(conv.inline(el)))
            continue
        element_id = str(el.get("id") or "")
        m = _ARTICLE_ID_RE.match(element_id) if el.name == "div" else None
        if m is None or "eli-subdivision" not in classes:
            continue
        number = m.group(1) + m.group(2)
        if not article_selected(number, articles):
            continue
        if pending_division:
            conv.out.heading(2, " ".join(pending_division))
            pending_division = []
        subtitle = el.find(class_="stitle-article-norm")
        name = _clean(conv.inline(subtitle)) if isinstance(subtitle, Tag) else ""
        conv.out.blocks.append(f"### Article {number} {name}".strip())
        conv.out.paragraphs += 1
        conv.article_body(el, number)
        found += 1
    if found == 0:
        raise ValueError(f"no article of {articles} found")
    return conv.out.result()


# ------------------------------------------------------------------- PRA Rulebook (UK)

_PRA_ARTICLE_RE = re.compile(r"^Article\s+(\d{1,4}[a-z]*)\b")
_PRA_SKIP_TEXT = {"[Deleted]", "[Note: Provision left blank]", "[deleted]"}
# The Rulebook writes display formulas in LaTeX: `\[K_b=\sqrt{...}\]`.
_PRA_DISPLAY_RE = re.compile(r"^\\\[(.+)\\\]$", re.S)


def _pra_inline(node: PageElement) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""
    if "visually-hidden" in _classes(node):
        return ""
    inner = "".join(_pra_inline(c) for c in node.children)
    if node.name == "sub":
        return f"_{{{_clean(inner)}}}"
    if node.name == "sup":
        return f"^{{{_clean(inner)}}}"
    if node.name == "img":
        # `-/media/<hash>.ashx`: a formula image served by the Rulebook (JPEG).
        media = _PRA_MEDIA_RE.search(str(node.get("src") or ""))
        return f" [formula: pra-{media.group(1)}.jpg] " if media else "[formula: image]"
    return inner


_PRA_MEDIA_RE = re.compile(r"-/media/([0-9a-f]{32})\.ashx")


def _pra_blocks(out: _Writer, node: Tag) -> None:
    for child in node.children:
        if isinstance(child, NavigableString):
            out.text(str(child))
            continue
        if not isinstance(child, Tag):
            continue
        if child.name == "table":
            out.table(_table_rows(child, _pra_inline))
        elif child.name in {"ol", "ul"}:
            for li in child.find_all("li", recursive=False):
                if isinstance(li, Tag):
                    nested = li.find(["ol", "ul", "table"])
                    if nested is None:
                        out.text(_pra_inline(li))
                    else:
                        _pra_blocks(out, li)
            for inner in child.find_all(["ol", "ul"], recursive=False):
                if isinstance(inner, Tag):
                    _pra_blocks(out, inner)
        elif child.name in {"p", "span", "em", "strong", "a", "li"}:
            text = _pra_inline(child)
            display = _PRA_DISPLAY_RE.match(text.strip())
            if display is not None:
                out.equation(display.group(1))
                continue
            out.formulas += text.count("[formula:")
            out.text(text)
        else:
            _pra_blocks(out, child)


def convert_pra(html: str, *, title: str) -> Conversion:
    """One PRA rule part: chapters, CRR-style articles and numbered rules, in order."""
    soup = BeautifulSoup(html, "html.parser")
    out = _Writer(title)
    article = ""
    blocks = soup.find_all("div", class_=["chapter-section", "row-block"])
    if not blocks:
        raise ValueError("no PRA rule block found")
    for block in blocks:
        if not isinstance(block, Tag):
            continue
        classes = _classes(block)
        row = block.find("div", class_="div-row", recursive=False)
        if not isinstance(row, Tag):
            continue
        number_el = row.find(class_="rule-number")
        number = _clean(number_el.get_text()) if isinstance(number_el, Tag) else ""
        body = row.find("div", class_="div-row__col-2")
        if not isinstance(body, Tag):
            continue
        if "chapter-section" in classes:
            heading_el = body.find("h3")
            heading = _clean(heading_el.get_text(" ")) if isinstance(heading_el, Tag) else ""
            m = _PRA_ARTICLE_RE.match(heading)
            if m is not None:
                article = m.group(1)
                out.blocks.append(f"### {heading}")
                out.paragraphs += 1
            elif heading:
                article = ""
                out.heading(2, f"{number} {heading}".strip())
            continue
        section_heading = body.find("h3", recursive=False)
        if isinstance(section_heading, Tag):
            article = ""
            out.heading(2, section_heading.get_text(" "))
            continue
        text = _clean(body.get_text(" "))
        if not text or text in _PRA_SKIP_TEXT:
            continue
        label = number.rstrip(".")
        if article and re.fullmatch(r"\d{1,3}[a-z]?", label):
            out.paragraph(f"Article {article}({label})")
        elif re.fullmatch(r"\d{1,2}\.\d{1,3}[A-Z]?", label):
            out.paragraph(f"Rule {label}")
        elif label:
            out.text(label)
        _pra_blocks(out, body)
    result = out.result()
    result.image_urls = {
        name: f"{PRA_ROOT}/-/media/{name.removeprefix('pra-').removesuffix('.jpg')}.ashx"
        for name in _IMAGE_PLACEHOLDER_RE.findall(result.markdown)
        if name.startswith("pra-")
    }
    return result


# ----------------------------------------------------------------- catalogue and runs


class CatalogEntry(BaseModel):
    """One document to build. `source` decides which of the selector fields apply."""

    doc_key: str
    source: Literal["ecfr", "eu", "pra"]
    jurisdiction: Jurisdiction
    title: str
    authors: list[str]
    doc_type: Literal["law", "guidance", "proposal"] = "law"
    topic: str
    year: int | None = None
    license: str
    valid_from: date | None = None
    valid_until: date | None = None
    # ecfr: title number, part, then `sections` (217.132…) or a `subpart` letter.
    cfr_title: int | None = None
    part: str | None = None
    sections: list[str] = []
    subpart: str | None = None
    # eu: CELEX of the consolidated text (02013R0575-20250629) and article ranges.
    celex: str | None = None
    articles: list[str] = []
    # pra: rule part slug and the date it is shown at.
    pra_part: str | None = None
    pra_date: date | None = None

    @model_validator(mode="after")
    def _selector(self) -> CatalogEntry:
        if self.source == "ecfr" and not (
            self.cfr_title and self.part and (self.sections or self.subpart)
        ):
            raise ValueError(f"{self.doc_key}: ecfr needs cfr_title, part, sections|subpart")
        if self.source == "eu" and not (self.celex and self.articles):
            raise ValueError(f"{self.doc_key}: eu needs celex and articles")
        if self.source == "pra" and not (self.pra_part and self.pra_date):
            raise ValueError(f"{self.doc_key}: pra needs pra_part and pra_date")
        return self


class Catalog(BaseModel):
    # eCFR point-in-time date; None: the latest issue of each title.
    ecfr_date: date | None = None
    documents: list[CatalogEntry]


def load_catalog(path: Path) -> Catalog:
    if not path.is_file():
        raise ValidationError(f"catalogue not found: {path}", details={"path": str(path)})
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        return Catalog.model_validate(raw)
    except ValueError as exc:
        raise ValidationError(
            f"invalid catalogue {path}: {exc}", details={"path": str(path)}
        ) from exc


class _Getter(Protocol):
    requests_made: int

    def get(self, url: str, headers: dict[str, str] | None = None) -> RawResponse: ...


def ecfr_urls(entry: CatalogEntry, issue_date: date) -> list[str]:
    base = f"{ECFR_ROOT}/api/versioner/v1/full/{issue_date.isoformat()}/title-{entry.cfr_title}.xml"
    if entry.subpart:
        return [f"{base}?part={entry.part}&subpart={entry.subpart}"]
    return [f"{base}?part={entry.part}&section={s}" for s in entry.sections]


def source_url(entry: CatalogEntry) -> str:
    if entry.source == "ecfr":
        if entry.subpart:
            part = f"title-{entry.cfr_title}/part-{entry.part}"
            return f"{ECFR_ROOT}/current/{part}/subpart-{entry.subpart}"
        return f"{ECFR_ROOT}/current/title-{entry.cfr_title}/section-{entry.sections[0]}"
    if entry.source == "eu":
        return f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{entry.celex}"
    assert entry.pra_date is not None
    return f"{PRA_ROOT}/pra-rules/{entry.pra_part}/{entry.pra_date.strftime('%d-%m-%Y')}"


def manifest_entry(entry: CatalogEntry, md_path: str) -> dict[str, object]:
    data: dict[str, object] = {
        "doc_key": entry.doc_key,
        "path": md_path,
        "title": entry.title,
        "authors": entry.authors,
        "year": entry.year,
        "doc_type": entry.doc_type,
        "topic": entry.topic,
        "source_url": source_url(entry),
        "license": entry.license,
    }
    if entry.valid_from:
        data["valid_from"] = entry.valid_from.isoformat()
    if entry.valid_until:
        data["valid_until"] = entry.valid_until.isoformat()
    return data


_MANIFEST_HEADER = (
    "# Generated by `kbase harvest-regulation` (WP21) from a catalogue in configs/harvest/,\n"
    "# then read by `kbase ingest`. Paths are relative to AGX_PATHS_DOCUMENTS_DIR; re-running\n"
    "# replaces an entry by its doc_key.\n"
)


def upsert_manifest(
    path: Path, jurisdiction: str, entries: list[dict[str, object]]
) -> tuple[int, int]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
    documents: list[dict[str, object]] = []
    if isinstance(raw, dict):
        documents = [d for d in raw.get("documents") or [] if isinstance(d, dict)]
    index = {d.get("doc_key"): i for i, d in enumerate(documents)}
    added = replaced = 0
    for entry in entries:
        position = index.get(entry["doc_key"])
        if position is None:
            index[entry["doc_key"]] = len(documents)
            documents.append(entry)
            added += 1
        else:
            documents[position] = entry
            replaced += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(
        {"collection": "regulation", "jurisdiction": jurisdiction, "documents": documents},
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )
    path.write_text(_MANIFEST_HEADER + "\n" + body, encoding="utf-8")
    return added, replaced


class DocumentReport(BaseModel):
    doc_key: str
    paragraphs: int
    tables: int
    formulas: int
    images: int
    bytes_md: int


class RegulationReport(BaseModel):
    selected: list[str]
    converted: list[DocumentReport] = []
    failed: dict[str, str] = {}
    manifests: dict[str, tuple[int, int]] = {}
    requests: int = 0


_HEADERS: dict[str, dict[str, str]] = {
    # The versioner API refuses uncompressed responses.
    "ecfr": {"Accept-Encoding": "gzip"},
    "eu": {"Accept": "application/xhtml+xml", "Accept-Language": "eng"},
    "pra": {},
}


def ecfr_latest_issues(client: _Getter) -> dict[int, date]:
    """Latest issue date of every CFR title, from the versioner API."""
    import json

    body = _fetch(client, f"{ECFR_ROOT}/api/versioner/v1/titles.json", "ecfr")
    titles = json.loads(body).get("titles", [])
    return {
        int(t["number"]): date.fromisoformat(t["latest_issue_date"])
        for t in titles
        if t.get("latest_issue_date")
    }


def _fetch(client: _Getter, url: str, source: str) -> str:
    response = client.get(url, headers=_HEADERS[source])
    if response.status != 200:
        raise DependencyError(
            f"HTTP {response.status} for {url}", details={"url": url, "status": response.status}
        )
    return response.body.decode("utf-8", errors="replace")


def harvest_regulation(
    client: _Getter,
    catalog: Catalog,
    *,
    documents_dir: Path,
    root_dir: str,
    manifest_dir: Path,
    only: list[str] | None = None,
    dry_run: bool = False,
) -> RegulationReport:
    """Builds the selected catalogue documents: raw source and Markdown under
    `<root_dir>/<jurisdiction>/`, formula images under `.../img/`, one manifest per
    jurisdiction (`manifest-regulation-<jurisdiction>.yaml`)."""
    selected = [e for e in catalog.documents if not only or e.doc_key in only]
    report = RegulationReport(selected=[e.doc_key for e in selected])
    if dry_run:
        return report
    latest: dict[int, date] = {}
    if catalog.ecfr_date is None and any(e.source == "ecfr" for e in selected):
        latest = ecfr_latest_issues(client)
    cache: dict[str, str] = {}
    entries: dict[str, list[dict[str, object]]] = {}
    for entry in selected:
        base = documents_dir / root_dir / entry.jurisdiction
        try:
            if entry.source == "ecfr":
                assert entry.cfr_title is not None
                issue_date = catalog.ecfr_date or latest.get(entry.cfr_title)
                if issue_date is None:
                    raise ValidationError(
                        f"no eCFR issue date for title {entry.cfr_title}", details={}
                    )
                parts = [_fetch(client, url, "ecfr") for url in ecfr_urls(entry, issue_date)]
                raw = "\n".join(parts)
                conversion = convert_ecfr(raw, title=entry.title)
                raw_name = f"{entry.doc_key}.xml"
            elif entry.source == "eu":
                assert entry.celex is not None
                if entry.celex not in cache:
                    cache[entry.celex] = _fetch(client, f"{CELLAR_ROOT}/{entry.celex}", "eu")
                raw = cache[entry.celex]
                conversion = convert_eu(
                    raw, title=entry.title, doc_key=entry.doc_key, articles=entry.articles
                )
                raw_name = f"{entry.celex}.xhtml"
            else:
                raw = _fetch(client, source_url(entry), "pra")
                conversion = convert_pra(raw, title=entry.title)
                raw_name = f"{entry.doc_key}.html"
        except (AppError, ValueError) as exc:
            report.failed[entry.doc_key] = str(exc)
            continue
        if conversion.paragraphs == 0:
            report.failed[entry.doc_key] = "no numbered paragraph found"
            continue
        (base / "raw").mkdir(parents=True, exist_ok=True)
        (base / "raw" / raw_name).write_text(raw, encoding="utf-8")
        md_rel = f"{root_dir}/{entry.jurisdiction}/md/{entry.doc_key}.md"
        (documents_dir / md_rel).parent.mkdir(parents=True, exist_ok=True)
        (documents_dir / md_rel).write_text(conversion.markdown, encoding="utf-8")
        if conversion.images or conversion.image_urls:
            (base / "img").mkdir(parents=True, exist_ok=True)
            for name, data in conversion.images.items():
                (base / "img" / name).write_bytes(data)
            for name, url in conversion.image_urls.items():
                target = base / "img" / name
                if target.exists():
                    continue
                response = client.get(url)
                if response.status == 200:
                    target.write_bytes(response.body)
        entries.setdefault(entry.jurisdiction, []).append(manifest_entry(entry, md_rel))
        report.converted.append(
            DocumentReport(
                doc_key=entry.doc_key,
                paragraphs=conversion.paragraphs,
                tables=conversion.tables,
                formulas=conversion.formulas,
                images=len(conversion.images) + len(conversion.image_urls),
                bytes_md=len(conversion.markdown.encode("utf-8")),
            )
        )
    for jurisdiction, items in entries.items():
        report.manifests[jurisdiction] = upsert_manifest(
            manifest_dir / f"manifest-regulation-{jurisdiction}.yaml", jurisdiction, items
        )
    report.requests = client.requests_made
    return report


# ------------------------------------------------------------- formula images (EU)

_IMAGE_PLACEHOLDER_RE = re.compile(r"\[formula: ([A-Za-z0-9_.-]+\.(?:jpg|png|gif))\]")
_MD_FORMULA_RE = re.compile(r"\$\$\s*(.+?)\s*\$\$|\$(.+?)\$", re.DOTALL)


def pending_images(img_dir: Path) -> list[Path]:
    """Formula images that have no LaTeX sidecar (`<image>.tex`) yet."""
    if not img_dir.is_dir():
        return []
    return sorted(
        p
        for p in img_dir.iterdir()
        if p.suffix in {".jpg", ".png", ".gif"} and not p.with_name(p.name + ".tex").exists()
    )


def latex_from_markdown(markdown: str) -> str:
    """The formula MinerU read from one image: its first `$$…$$` or `$…$`, cleaned; ""
    when it found none (the placeholder then stays)."""
    match = _MD_FORMULA_RE.search(markdown)
    if match is None:
        return ""
    return clean_latex(match.group(1) or match.group(2) or "")


def apply_image_formulas(markdown: str, img_dir: Path) -> tuple[str, int, int]:
    """Replaces each `[formula: <image>]` whose sidecar holds LaTeX by `$<latex>$`;
    returns (markdown, placed, placeholders)."""
    placed = 0
    total = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal placed, total
        total += 1
        sidecar = img_dir / f"{match.group(1)}.tex"
        latex = sidecar.read_text(encoding="utf-8").strip() if sidecar.is_file() else ""
        if not latex:
            return match.group(0)
        placed += 1
        return f"${latex}$"

    return _IMAGE_PLACEHOLDER_RE.sub(_sub, markdown), placed, total


def convert_images(images: list[Path], *, mineru: Path, timeout_s: float) -> dict[str, str]:
    """One MinerU run over all `images` (loading its models once), then one LaTeX
    sidecar per image, empty when MinerU found no formula. Returns name -> LaTeX."""
    import shutil
    import subprocess
    import tempfile

    if not images:
        return {}
    if not mineru.is_file():
        raise DependencyError(f"MinerU not found: {mineru}", details={"path": str(mineru)})
    found: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in"
        out = Path(tmp) / "out"
        src.mkdir()
        for image in images:
            shutil.copy2(image, src / image.name)
        args = [str(mineru), "-p", str(src), "-o", str(out), "-b", "pipeline", "-m", "ocr"]
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise DependencyError("MinerU timed out on formula images", details={}) from exc
        if result.returncode != 0:
            raise DependencyError(
                f"MinerU failed on formula images: {result.stderr.strip()[-500:]}", details={}
            )
        for image in images:
            outputs = sorted(out.rglob(f"{image.stem}.md"))
            latex = latex_from_markdown(outputs[0].read_text("utf-8")) if outputs else ""
            image.with_name(image.name + ".tex").write_text(latex + "\n", encoding="utf-8")
            found[image.name] = latex
    return found
