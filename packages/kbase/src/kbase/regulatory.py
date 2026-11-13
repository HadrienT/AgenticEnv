"""Regulatory paragraph ids (WP20 §6): what a citation of a prudential text points to.

The Basel Framework numbers every paragraph inside a chapter (`MAR21.4` is paragraph 4
of chapter 21 of the market risk standard); EU regulations and the PRA's CRR parts
number articles and their paragraphs (`Article 274(2)`); other PRA parts number rules
(`Rule 2.1`); the US Code of Federal Regulations numbers sections and nested paragraphs
(`§ 217.132(c)(1)`, WP21 §4). The regulation converters write each paragraph as its own
heading, so a chunk's paragraph ids are read from the titles of the sections it covers.
"""

from __future__ import annotations

import re

# Standards of the consolidated Basel Framework (bis.org, 2026).
BASEL_STANDARDS = (
    "BCP", "CAP", "CRE", "DIS", "LCR", "LEV", "LEX", "MAR", "MGN", "NSF", "OPE", "RBC",
    "SCO", "SRP",
)  # fmt: skip
_STANDARD = "|".join(BASEL_STANDARDS)

# `217.132`, `240.18a-1`: a CFR section number (part.section).
_CFR_SECTION = r"\d{1,3}\.\d{1,4}[a-z]?(?:-\d{1,2})?"
# `(c)(1)(ii)(A)`: a CFR paragraph path.
_CFR_PATH = r"(?:\([a-zA-Z0-9]{1,5}\))*"

# A section title that *is* a paragraph: `MAR21.4`, `CRE52.12a`, `Article 325c`,
# `Article 274(2)`, `Rule 2.1`, `§ 217.132(c)(1)`.
_TITLE_ID_RE = re.compile(
    rf"^(?:(?P<basel>(?:{_STANDARD})\d{{1,3}}\.\d{{1,3}}[a-z]?)"
    r"|Article\s+(?P<article>\d{1,4}[a-z]*)(?P<article_par>\(\d{1,3}[a-z]?\))?"
    r"|Rule\s+(?P<rule>\d{1,2}\.\d{1,3}[A-Z]?)"
    rf"|§\s*(?P<cfr>{_CFR_SECTION})(?P<cfr_path>{_CFR_PATH}))"
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


# `Art. 274(2)`, `art 274`, `article 274 paragraph 2`: how people write an article.
_ARTICLE_RE = re.compile(
    r"\b(?:Art\.?|Article)\s*(\d{1,4}[a-z]*)(?:\s*\((\d{1,3}[a-z]?)\)|\s+(?:paragraph|para\.?)\s+(\d{1,3}))?",
    re.IGNORECASE,
)
# `12 CFR 217.132(c)`, `12 C.F.R. § 217.132`, `section 217.132`, `§217.132`.
_CFR_REF_RE = re.compile(
    rf"(?:\b\d{{1,2}}\s+C\.?F\.?R\.?\s*(?:§+\s*|(?:part|section)\s+)?|\bsection\s+|§+\s*)"
    rf"({_CFR_SECTION})({_CFR_PATH})",
    re.IGNORECASE,
)

# A canonical Basel paragraph id inside free text (`MAR33.3`), any case.
_ID_TOKEN_RE = re.compile(rf"\b(?:{_STANDARD})\d{{1,3}}\.\d{{1,3}}[a-z]?\b", re.IGNORECASE)
_ARTICLE_TOKEN_RE = re.compile(r"\bArticle\s+(\d{1,4}[a-z]*)", re.IGNORECASE)
_CFR_TOKEN_RE = re.compile(rf"§\s*({_CFR_SECTION})")


def paragraph_tokens(text: str) -> list[str]:
    """Full-text query terms for the paragraph ids in `text`, as the index stores them:
    `mar33.3`; `article <-> 274` (the index splits `Article 274(2)` into words);
    `217.132` (one token for a CFR section). Call on normalised text
    (`normalize_paragraph_refs`) to catch the spelled-out forms too."""
    tokens = [m.group(0).lower() for m in _ID_TOKEN_RE.finditer(text)]
    tokens += [f"article <-> {m.group(1).lower()}" for m in _ARTICLE_TOKEN_RE.finditer(text)]
    tokens += [m.group(1).lower() for m in _CFR_TOKEN_RE.finditer(text)]
    return tokens


def paragraph_id(title: str) -> str | None:
    """The paragraph id a section title names, normalised, or None for an ordinary title."""
    match = _TITLE_ID_RE.match(title.strip())
    if match is None:
        return None
    if match.group("basel"):
        return match.group("basel")
    if match.group("article"):
        return f"Article {match.group('article')}{match.group('article_par') or ''}"
    if match.group("rule"):
        return f"Rule {match.group('rule')}"
    return f"§ {match.group('cfr')}{match.group('cfr_path')}"


def _article(match: re.Match[str]) -> str:
    paragraph = match.group(2) or match.group(3)
    return f"Article {match.group(1)}" + (f"({paragraph})" if paragraph else "")


def normalize_paragraph_refs(query: str) -> str:
    """Rewrites spelled-out references to their canonical id (`MAR21.4`,
    `Article 274(2)`, `§ 217.132(c)`), so lexical search matches the tokens the chunk
    carries. Other text is left as is."""
    query = _OF_RE.sub(lambda m: f"{m.group(2).upper()}{m.group(1)}", query)
    query = _SPACED_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}", query)
    query = _ARTICLE_RE.sub(_article, query)
    return _CFR_REF_RE.sub(lambda m: f"§ {m.group(1)}{m.group(2)}", query)


def matches_prefix(paragraph: str, prefix: str) -> bool:
    """`MAR21` covers `MAR21.4`; `MAR21.4` covers itself (and `MAR21.4a`), not `MAR21.40`.
    `Article 274` covers `Article 274(2)`; `§ 217.132(c)` covers `§ 217.132(c)(1)`, not
    `§ 217.1320`."""
    if paragraph == prefix:
        return True
    if not paragraph.startswith(prefix):
        return False
    rest = paragraph[len(prefix) :]
    return rest[0] in ".(" or (rest.isalpha() and rest.islower())
