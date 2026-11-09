"""Heading levels for the Markdown parser.

MinerU writes nearly every heading of a book at the same level (`## 2.1`, `## 2.1.1`,
`## Bias`), repeats running headers as headings (`## 2 Generating Random Numbers` in
the middle of chapter 2) and turns stray lines into headings (`## 1, 3, 9, 5, 4, 1`).
`plan_headings` rebuilds the tree from the numbering when the Markdown levels cannot
be trusted, and says which heading lines are noise. LaTeXML output (arXiv harvest)
has levels that agree with its numbering, so it is left as written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_NUMBER_RE = re.compile(r"^(?:chapter\s+|section\s+)?(\d{1,2}(?:\.\d{1,3})*)\.?\s+(?=\S)", re.I)
_HAS_LETTER_RE = re.compile(r"[^\W\d_]{2,}", re.UNICODE)
# Share of numbered headings whose Markdown level matches their numbering depth above
# which the document's own levels are kept.
_TRUSTED_SHARE = 0.8

HeadingAction = Literal["heading", "text", "drop"]


@dataclass(frozen=True)
class HeadingPlan:
    action: HeadingAction
    level: int = 0


@dataclass(frozen=True)
class _Raw:
    line_no: int
    md_level: int
    title: str
    number: str | None


def _number(title: str) -> str | None:
    match = _NUMBER_RE.match(title)
    return match.group(1) if match else None


def plan_headings(lines: list[str]) -> dict[int, HeadingPlan]:
    """Maps the line number of every `#` heading to what the parser should do with it."""
    raws: list[_Raw] = []
    plan: dict[int, HeadingPlan] = {}
    for line_no, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if not match:
            continue
        title = match.group(2).strip()
        if not _HAS_LETTER_RE.search(title):
            plan[line_no] = HeadingPlan("text")  # `## 1, 3, 9, 5, 4, 1, ... ,`
            continue
        raws.append(_Raw(line_no, len(match.group(1)), title, _number(title)))

    depths = [(r.md_level, r.number.count(".") + 2) for r in raws if r.number is not None]
    consistent = sum(1 for md_level, depth in depths if md_level == depth)
    trusted = not depths or consistent / len(depths) >= _TRUSTED_SHARE

    # Unnumbered headings met before any numbered one (Preface, Contents, Foundations)
    # sit beside the shallowest numbered sections, never above them: otherwise
    # `Contents` would become the parent of `1.1`, and curation would drop the book.
    shallowest = min((depth for _, depth in depths), default=2)
    seen_numbers: set[str] = set()
    last_numbered_level: int | None = None
    first = True
    for raw in raws:
        if raw.number is not None:
            if raw.number in seen_numbers:
                plan[raw.line_no] = HeadingPlan("drop")  # running header
                continue
            seen_numbers.add(raw.number)
        if trusted:
            level = raw.md_level
        elif first and raw.md_level == 1:
            level = 1  # the document title
        elif raw.number is not None:
            level = raw.number.count(".") + 2
        elif raw.md_level == 1:
            level = 2  # an unnumbered chapter
        elif last_numbered_level is not None:
            level = min(last_numbered_level + 1, 6)
        else:
            level = shallowest
        if raw.number is not None or (not trusted and raw.md_level == 1 and not first):
            last_numbered_level = level
        first = False
        plan[raw.line_no] = HeadingPlan("heading", level)
    return plan
