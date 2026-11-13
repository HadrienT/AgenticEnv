"""Shared pieces of the regulation converters (WP21): cleaning, the Markdown writer
(one heading per numbered paragraph), tables, and article ranges."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from bs4.element import PageElement, Tag

_WS_RE = re.compile(r"\s+")


def clean(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def escape(line: str) -> str:
    """A line starting with these would be re-read as structure by `MarkdownParser`."""
    return "\\" + line if line.startswith(("#", "$$", "|", "<!--")) else line


def classes(el: Tag) -> set[str]:
    value = el.get("class")
    if isinstance(value, str):
        return set(value.split())
    return set(value or [])


def pipe_table(rows: list[list[str]]) -> str | None:
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        return None
    width = max(len(r) for r in rows)
    padded = [[c.replace("|", "\\|") for c in r] + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(padded[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in padded[1:]]
    return "\n".join(lines)


def table_rows(table: Tag, inline: Callable[[PageElement], str]) -> list[list[str]]:
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
            cells.append(clean(inline(cell)))
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


class Writer:
    """Accumulates Markdown blocks separated by blank lines."""

    def __init__(self, title: str) -> None:
        self.blocks: list[str] = [f"# {title}"]
        self.paragraphs = 0
        self.tables = 0
        self.formulas = 0
        self.images: dict[str, bytes] = {}

    def heading(self, level: int, text: str) -> None:
        self.blocks.append(f"{'#' * level} {clean(text)}")

    def paragraph(self, pid: str, title: str = "") -> None:
        self.paragraphs += 1
        self.heading(4, f"{pid} {title}".strip())

    def text(self, text: str) -> None:
        cleaned = clean(text)
        if cleaned:
            self.blocks.append(escape(cleaned))

    def equation(self, latex: str) -> None:
        self.formulas += 1
        self.blocks.append(f"$$\n{latex.strip()}\n$$")

    def table(self, rows: list[list[str]]) -> None:
        md = pipe_table(rows)
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


_ARTICLE_NUM_RE = re.compile(r"^(\d{1,4})([a-z]*)$")


def article_key(number: str) -> tuple[int, int, str]:
    m = _ARTICLE_NUM_RE.match(number)
    if m is None:
        raise ValueError(f"not an article number: {number}")
    return int(m.group(1)), len(m.group(2)), m.group(2)


def article_selected(number: str, ranges: list[str]) -> bool:
    """`ranges`: `"271-311"`, `"325-325bp"`, `"105"`; letters order `325 < 325a < 325z
    < 325aa`, as the CRR numbers inserted articles."""
    key = article_key(number)
    for spec in ranges:
        low, _, high = spec.partition("-")
        if article_key(low.strip()) <= key <= article_key((high or low).strip()):
            return True
    return False
