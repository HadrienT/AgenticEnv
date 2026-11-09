"""The text a chunk is embedded and reranked with: its content headed by where it comes
from. `Glasserman, Monte Carlo Methods… › 2.3 Normal Random Variables › Box-Muller
Method` tells both models what a passage like "generate two uniforms and …" is about,
which the passage alone often does not. The stored `content` stays the raw text."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from kbase.schemas import Section

PATH_SEPARATOR = " › "


def section_paths(sections: Iterable[Section]) -> dict[str, list[str]]:
    """Section id → titles from the outermost chapter down, the document title (level 1)
    left out since it is given separately."""
    by_id = {s.section_id: s for s in sections}
    paths: dict[str, list[str]] = {}
    for section in by_id.values():
        titles: list[str] = []
        current: Section | None = section
        while current is not None:
            if current.level > 1:
                titles.insert(0, current.title)
            current = by_id.get(current.parent_id) if current.parent_id else None
        paths[section.section_id] = titles
    return paths


def contextual_text(document_title: str, path: Sequence[str], content: str) -> str:
    header = document_title if not path else document_title + "\n" + PATH_SEPARATOR.join(path)
    return f"{header}\n\n{content}"
