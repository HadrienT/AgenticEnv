"""Regulatory paragraph ids (WP20 §6): what a citation of a prudential text points to.

The Basel Framework numbers every paragraph inside a chapter (`MAR21.4` is paragraph 4
of chapter 21 of the market risk standard); EU regulations number articles
(`Article 325c`). The regulation converters write each paragraph as its own heading,
so a chunk's paragraph ids are read from the titles of the sections it covers.
"""

from __future__ import annotations

import re

# Standards of the consolidated Basel Framework (bis.org, 2026).
BASEL_STANDARDS = (
    "BCP", "CAP", "CRE", "DIS", "LCR", "LEV", "LEX", "MAR", "MGN", "NSF", "OPE", "RBC",
    "SCO", "SRP",
)  # fmt: skip
_STANDARD = "|".join(BASEL_STANDARDS)

# A section title that *is* a paragraph: `MAR21.4`, `CRE52.12a`, `Article 325c`.
_TITLE_ID_RE = re.compile(
    rf"^(?:(?P<basel>(?:{_STANDARD})\d{{1,3}}\.\d{{1,3}}[a-z]?)|Article\s+(?P<article>\d{{1,4}}[a-z]*))"
    r"(?=\s|$|[.:])"
)

# How people write a Basel paragraph in a question: `MAR 21.4`, `paragraph 21.4 of MAR`,
# `MAR para 21.4`. The canonical form `MAR21.4` is what lexical search indexes.
_SPACED_RE = re.compile(
    rf"\b({_STANDARD})\s+(?:paragraphs?\s+|paras?\.?\s+|§\s*)?(\d{{1,3}}\.\d{{1,3}}[a-z]?)\b"
)
_OF_RE = re.compile(
    rf"\b(?:paragraphs?|paras?\.?|§)\s*(\d{{1,3}}\.\d{{1,3}}[a-z]?)\s+(?:of|in|du|de)\s+(?:the\s+)?({_STANDARD})\b",
    re.IGNORECASE,
)


def paragraph_id(title: str) -> str | None:
    """The paragraph id a section title names, normalised, or None for an ordinary title."""
    match = _TITLE_ID_RE.match(title.strip())
    if match is None:
        return None
    if match.group("basel"):
        return match.group("basel")
    return f"Article {match.group('article')}"


def normalize_paragraph_refs(query: str) -> str:
    """Rewrites spelled-out Basel references to their canonical id (`MAR21.4`), so
    lexical search matches the token the chunk carries. Other text is left as is."""
    query = _OF_RE.sub(lambda m: f"{m.group(2).upper()}{m.group(1)}", query)
    return _SPACED_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}", query)


def matches_prefix(paragraph: str, prefix: str) -> bool:
    """`MAR21` covers `MAR21.4`; `MAR21.4` covers itself (and `MAR21.4a`), not `MAR21.40`."""
    if paragraph == prefix:
        return True
    if not paragraph.startswith(prefix):
        return False
    rest = paragraph[len(prefix) :]
    return rest[0] == "." or (rest.isalpha() and rest.islower())
