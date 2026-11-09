"""Drops the sections of a parsed document that carry no knowledge worth retrieving:
tables of contents, prefaces, acknowledgements, indexes, bibliographies, exercise
lists, teaching notes. A dropped section takes its whole subtree with it.

Patterns are case-insensitive regexes matched against the whole section title, once
its leading number (`12.8 Exercises`) is removed. Global patterns come from
`curation.drop_sections` in the kbase config; a manifest entry can add its own
(`exclude_sections`) for a book's specific chapters.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from kbase.schemas import ParsedDocument

_LEADING_NUMBER_RE = re.compile(r"^(?:chapter\s+)?\d{1,2}(?:\.\d{1,3})*\.?\s+", re.I)


def _normalize(title: str) -> str:
    return _LEADING_NUMBER_RE.sub("", title.strip()).strip(" .:*_")


def compile_patterns(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.I) for p in patterns]


def drop_sections(doc: ParsedDocument, patterns: list[re.Pattern[str]]) -> ParsedDocument:
    """A copy of `doc` without the matching sections, their descendants and their blocks."""
    if not patterns:
        return doc
    dropped: set[str] = set()
    for section in doc.sections:  # parents come before children
        if section.parent_id in dropped:
            # A numbered heading is content even under a dropped one (a `1.1` that a
            # badly leveled `Contents` swallowed): it and its subtree stay.
            if not _LEADING_NUMBER_RE.match(section.title.strip()):
                dropped.add(section.section_id)
        elif section.level > 1 and any(p.fullmatch(_normalize(section.title)) for p in patterns):
            # Level 1 is the document title, under which MinerU sometimes nests the whole
            # book (`# Front matter`): dropping it would drop everything.
            dropped.add(section.section_id)
    if not dropped:
        return doc
    return doc.model_copy(
        update={
            "sections": [s for s in doc.sections if s.section_id not in dropped],
            "blocks": [b for b in doc.blocks if b.section_id not in dropped],
        }
    )
