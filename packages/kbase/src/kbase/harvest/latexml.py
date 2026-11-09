"""LaTeXML HTML (arxiv.org/html, ar5iv) → the Markdown dialect `MarkdownParser` reads.

Rules in blueprint/wp/WP18-arxiv-harvest.md §5. Formulas are taken from `alttext`, the
authors' LaTeX, never from the MathML; equation numbers from `ltx_tag_equation`.
Paragraphs are written on one line each, so no line of prose can be read back as a
heading, an equation fence or a table row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup
from bs4.element import NavigableString, PageElement, Tag

_WS_RE = re.compile(r"\s+")
_DISPLAYSTYLE_RE = re.compile(r"\\(?:displaystyle|textstyle)\b\s*")
_EQ_NUMBER_RE = re.compile(r"^\(?\s*([^()]+?)\s*\)?$")
_PUNCT_AFTER_MATH_RE = re.compile(r"\$ +([.,;:!?)\]])")
_OPEN_BEFORE_MATH_RE = re.compile(r"([(\[]) +\$")
# Elements whose whole subtree carries no content worth indexing.
_DROP_CLASSES = frozenset(
    {
        "ltx_bibliography", "ltx_authors", "ltx_dates", "ltx_page_navbar", "ltx_TOC",
        "ltx_page_footer", "ltx_page_header", "ltx_note", "ltx_role_refnum",
        "ltx_classification", "ltx_pagination", "ltx_ERROR",
    }
)  # fmt: skip
_DROP_TAGS = frozenset({"nav", "footer", "header", "script", "style", "button", "svg", "img"})
_HEADING_TAGS = frozenset({"h2", "h3", "h4", "h5"})


@dataclass(frozen=True)
class Conversion:
    markdown: str
    sections: int
    equations: int
    text_chars: int
    has_abstract: bool


def _classes(el: Tag) -> set[str]:
    value = el.get("class")
    if isinstance(value, str):
        return {value}
    return set(value or [])


def _is_dropped(el: Tag) -> bool:
    return el.name in _DROP_TAGS or bool(_classes(el) & _DROP_CLASSES)


def _clean_ws(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def _latex(math: Tag) -> str:
    alttext = math.get("alttext")
    raw = alttext if isinstance(alttext, str) else math.get_text()
    return _clean_ws(_DISPLAYSTYLE_RE.sub("", raw))


def _inline(node: PageElement) -> str:
    """Text of an inline subtree; math becomes `$latex$`."""
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag) or _is_dropped(node):
        return ""
    if node.name == "math":
        latex = _latex(node)
        return f" ${latex}$ " if latex else ""
    if node.name == "br":
        return " "
    text = "".join(_inline(child) for child in node.children)
    if "ltx_tag" in _classes(node):  # "1" in "1 Introduction", "Figure 2:" in captions
        text += " "
    return text


def _paragraph(text: str) -> str | None:
    # Inline math is padded with spaces; take them back where punctuation follows.
    cleaned = _PUNCT_AFTER_MATH_RE.sub(r"$\1", _clean_ws(text))
    cleaned = _OPEN_BEFORE_MATH_RE.sub(r"\1$", cleaned)
    if not cleaned:
        return None
    # A line starting with these would be re-read as structure by MarkdownParser.
    if cleaned.startswith(("#", "$$", "|", "<!--")):
        cleaned = "\\" + cleaned
    return cleaned


def _equation_rows(table: Tag) -> list[tuple[str, str | None]]:
    """(latex, number) per row of an `ltx_equation` / `ltx_equationgroup` table."""
    rows: list[tuple[str, str | None]] = []
    for row in table.find_all("tr"):
        if not isinstance(row, Tag) or "ltx_eqn_row" not in _classes(row):
            continue
        parts: list[str] = []
        number: str | None = None
        for cell in row.find_all("td", recursive=False):
            if not isinstance(cell, Tag):
                continue
            if "ltx_eqn_eqno" in _classes(cell):
                tag_text = _clean_ws(cell.get_text())
                match = _EQ_NUMBER_RE.match(tag_text)
                number = match.group(1) if match and tag_text else None
                continue
            for math in cell.find_all("math"):
                if isinstance(math, Tag):
                    parts.append(_latex(math))
        latex = " ".join(p for p in parts if p)
        if latex:
            rows.append((latex, number))
    return rows


def _table_md(table: Tag) -> str | None:
    rows: list[list[str]] = []
    for row in table.find_all("tr"):
        if not isinstance(row, Tag):
            continue
        cells = [
            _clean_ws(_inline(cell)).replace("|", "\\|")
            for cell in row.find_all(["td", "th"], recursive=False)
            if isinstance(cell, Tag)
        ]
        if any(cells):
            rows.append(cells)
    if len(rows) < 2:
        return None
    width = max(len(r) for r in rows)
    padded = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(padded[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in padded[1:]]
    return "\n".join(lines)


class _Writer:
    def __init__(self) -> None:
        self.blocks: list[str] = []
        self.sections = 0
        self.equations = 0
        self.text_chars = 0
        self.has_abstract = False

    def text(self, raw: str) -> None:
        paragraph = _paragraph(raw)
        if paragraph:
            self.blocks.append(paragraph)
            self.text_chars += len(paragraph)

    def heading(self, level: int, raw: str) -> None:
        title = _clean_ws(raw)
        if title:
            self.blocks.append(f"{'#' * level} {title}")
            if level >= 2:
                self.sections += 1

    def equation(self, latex: str, number: str | None) -> None:
        close = f"$$ ({number})" if number else "$$"
        self.blocks.append(f"$$\n{latex}\n{close}")
        self.equations += 1

    def raw_block(self, block: str) -> None:
        self.blocks.append(block)


def _walk(el: Tag, out: _Writer) -> None:
    for child in el.children:
        if isinstance(child, NavigableString):
            if child.strip():
                out.text(str(child))
            continue
        if not isinstance(child, Tag) or _is_dropped(child):
            continue
        _block(child, out)


def _block(el: Tag, out: _Writer) -> None:
    classes = _classes(el)
    name = el.name
    if name == "h1":
        out.heading(1, _inline(el))
    elif name in _HEADING_TAGS:
        out.heading(int(name[1]), _inline(el))
    elif "ltx_abstract" in classes:
        out.heading(2, "Abstract")
        out.has_abstract = True
        for child in el.children:
            if isinstance(child, Tag) and child.name == "h6":
                continue  # the "Abstract" title itself
            if isinstance(child, Tag):
                _block(child, out)
    elif name == "h6":  # theorem / proof / abstract titles: prose, not sections
        out.text(_inline(el))
    elif name == "table" and classes & {"ltx_equation", "ltx_equationgroup"}:
        for latex, number in _equation_rows(el):
            out.equation(latex, number)
    elif name == "math":
        latex = _latex(el)
        if latex:
            out.equation(latex, None)
    elif name == "table" or "ltx_tabular" in classes:
        table = _table_md(el)
        if table:
            out.raw_block(table)
        else:
            out.text(_inline(el))
    elif name == "figure":
        caption = el.find("figcaption")
        if isinstance(caption, Tag):
            out.text(_inline(caption))
        for inner in el.find_all("table"):
            if isinstance(inner, Tag) and "ltx_tabular" in _classes(inner):
                md = _table_md(inner)
                if md:
                    out.raw_block(md)
        if "ltx_float_algorithm" in classes or el.find(class_="ltx_listing"):
            for line in el.find_all(class_="ltx_listingline"):
                if isinstance(line, Tag):
                    out.text(_inline(line))
    elif name == "p" or "ltx_listingline" in classes:
        _paragraph_with_math(el, out)
    elif name in {"ul", "ol"}:
        for item in el.find_all("li", recursive=False):
            if isinstance(item, Tag):
                out.text("- " + _clean_ws(_inline(item)).lstrip("•∙◦▪–- ").strip())
    else:
        _walk(el, out)


def _paragraph_with_math(el: Tag, out: _Writer) -> None:
    """A `<p>` is prose, but LaTeXML sometimes nests display equations inside one."""
    buffer: list[str] = []
    for child in el.children:
        if (
            isinstance(child, Tag)
            and child.name == "table"
            and (_classes(child) & {"ltx_equation", "ltx_equationgroup"})
        ):
            out.text("".join(buffer))
            buffer.clear()
            _block(child, out)
        else:
            buffer.append(_inline(child))
    out.text("".join(buffer))


def convert(html: str, *, title: str, abstract: str | None = None) -> Conversion:
    """`title` (from the API) heads the document; `abstract` fills in a missing one."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("article") or soup.body or soup
    out = _Writer()
    out.heading(1, title)
    if isinstance(root, Tag):
        for h1 in root.find_all("h1"):
            if isinstance(h1, Tag):
                h1.decompose()  # the API title is already the document heading
        _walk(root, out)
    if not out.has_abstract and abstract:
        out.blocks.insert(1, "## Abstract")
        out.blocks.insert(2, _paragraph(abstract) or "")
        out.sections += 1
        out.has_abstract = True
    markdown = "\n\n".join(b for b in out.blocks if b) + "\n"
    return Conversion(
        markdown=markdown,
        sections=out.sections,
        equations=out.equations,
        text_chars=out.text_chars,
        has_abstract=out.has_abstract,
    )
