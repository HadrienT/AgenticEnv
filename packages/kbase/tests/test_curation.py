from __future__ import annotations

from kbase.ingestion.curation import compile_patterns, drop_sections
from kbase.schemas import ContentBlock, DocumentMeta, ParsedDocument, Section


def _doc() -> ParsedDocument:
    def section(sid: str, parent: str | None, level: int, title: str) -> Section:
        return Section(
            section_id=sid, parent_id=parent, level=level, ordinal=1, title=title, path=sid
        )

    sections = [
        section("1", None, 1, "Front matter"),
        section("1.1", "1", 2, "Contents"),
        section("1.2", "1", 2, "1 Monte Carlo"),
        section("1.2.1", "1.2", 3, "1.9 Exercises"),
        section("1.2.1.1", "1.2.1", 4, "Exercise 1.1"),
        section("1.2.2", "1.2", 3, "1.2 Variance reduction"),
    ]
    blocks = [
        ContentBlock(kind="text", text=f"text of {s.section_id}", section_id=s.section_id)
        for s in sections
    ]
    meta = DocumentMeta(doc_key="k", title="t", doc_type="book")
    return ParsedDocument(
        meta=meta, version="1", sha256="x", page_count=None, sections=sections, blocks=blocks,
        parser_name="markdown", parser_version="2",
    )  # fmt: skip


def test_matching_sections_and_their_subtrees_are_dropped() -> None:
    patterns = compile_patterns(["(table of )?contents", "exercises?", "front matter"])
    kept = drop_sections(_doc(), patterns)
    assert [s.section_id for s in kept.sections] == ["1", "1.2", "1.2.2"]
    assert [b.section_id for b in kept.blocks] == ["1", "1.2", "1.2.2"]


def test_no_patterns_keeps_everything() -> None:
    doc = _doc()
    assert drop_sections(doc, []) is doc
