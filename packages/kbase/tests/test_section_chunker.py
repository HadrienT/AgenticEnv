from __future__ import annotations

from kbase.contextual import contextual_text, section_paths
from kbase.ingestion.chunking import SectionChunker
from kbase.schemas import ChunkPolicy, ContentBlock, DocumentMeta, Equation, ParsedDocument, Section

_POLICY = ChunkPolicy(
    strategy="section", target_tokens=60, max_tokens=120, min_tokens=20, overlap_tokens=12
)


def _section(sid: str, parent: str | None, level: int, title: str) -> Section:
    return Section(section_id=sid, parent_id=parent, level=level, ordinal=1, title=title, path=sid)


def _text(sid: str, words: int, tag: str = "w") -> ContentBlock:
    sentence = " ".join(f"{tag}{i}" for i in range(9)) + "."
    return ContentBlock(kind="text", text=" ".join([sentence] * (words // 10)), section_id=sid)


def _doc(sections: list[Section], blocks: list[ContentBlock]) -> ParsedDocument:
    return ParsedDocument(
        meta=DocumentMeta(doc_key="k", title="Book", doc_type="book"), version="1", sha256="x",
        page_count=None, sections=sections, blocks=blocks, parser_name="m", parser_version="2",
    )  # fmt: skip


def test_equations_stay_inline_with_their_prose_and_are_recorded() -> None:
    sections = [_section("1", None, 1, "Book"), _section("1.1", "1", 2, "2.3 Box-Muller")]
    eq = Equation(latex="Z = \\sqrt{-2 \\ln U_1} \\cos(2\\pi U_2)", equation_number="2.24")
    blocks = [
        ContentBlock(kind="text", text="Two uniforms give two normals:", section_id="1.1"),
        ContentBlock(kind="equation", text=eq.latex, section_id="1.1", equation=eq),
        ContentBlock(kind="text", text="which are independent.", section_id="1.1"),
    ]
    (chunk,) = SectionChunker().chunk(_doc(sections, blocks), _POLICY)
    assert chunk.content.startswith("## 2.3 Box-Muller\n\nTwo uniforms give two normals:")
    assert "$$ Z = \\sqrt{-2 \\ln U_1} \\cos(2\\pi U_2) $$ (2.24)\n\nwhich are independent." in (
        chunk.content
    )
    assert chunk.kind == "text" and chunk.has_equations
    assert [e.equation.equation_number for e in chunk.equations] == ["2.24"]


def test_long_sections_split_with_overlap_and_short_siblings_merge() -> None:
    sections = [
        _section("1", None, 1, "Book"),
        _section("1.1", "1", 2, "Chapter"),
        _section("1.1.1", "1.1", 3, "Short A"),
        _section("1.1.2", "1.1", 3, "Short B"),
        _section("1.1.3", "1.1", 3, "Long"),
    ]
    blocks = [_text("1.1.1", 10, "a"), _text("1.1.2", 10, "b")]
    blocks += [_text("1.1.3", 40, "c"), _text("1.1.3", 40, "d"), _text("1.1.3", 40, "e")]
    chunks = SectionChunker().chunk(_doc(sections, blocks), _POLICY)
    assert "### Short A" in chunks[0].content and "### Short B" in chunks[0].content
    long_chunks = [c for c in chunks if c.section_id == "1.1.3"]
    assert len(long_chunks) >= 2
    # The continuation starts with the last sentence of the previous chunk.
    tail = long_chunks[0].content.rsplit(". ", 1)[-1]
    assert long_chunks[1].content.startswith(tail.split(".")[0])
    assert all(c.n_tokens <= _POLICY.max_tokens + 40 for c in chunks)


def test_contextual_text_heads_content_with_document_and_path() -> None:
    sections = [
        _section("1", None, 1, "Book"),
        _section("1.1", "1", 2, "2 Random"),
        _section("1.1.1", "1.1", 3, "2.3 Normals"),
    ]
    paths = section_paths(sections)
    assert paths["1.1.1"] == ["2 Random", "2.3 Normals"] and paths["1"] == []
    assert contextual_text("Glasserman", paths["1.1.1"], "body") == (
        "Glasserman\n2 Random › 2.3 Normals\n\nbody"
    )
    assert contextual_text("Glasserman", [], "body") == "Glasserman\n\nbody"


def test_an_oversized_table_is_cut_between_rows_and_repeats_its_header() -> None:
    rows = [f"| {i} | {i * 0.123456:.6f} | {i * 9.87:.4f} |" for i in range(120)]
    table = "\n".join(["| N | error | time |", "|---|---|---|", *rows])
    sections = [_section("1", None, 1, "Paper"), _section("1.1", "1", 2, "5 Results")]
    blocks = [
        ContentBlock(
            kind="table",
            text=table,
            section_id="1.1",
            table_caption="Table 4: Convergence",
            table_content_md=table,
        )  # fmt: skip
    ]
    chunks = SectionChunker().chunk(_doc(sections, blocks), _POLICY)
    assert len(chunks) > 3
    assert all(c.n_tokens <= _POLICY.max_tokens + 40 for c in chunks)
    assert "Table 4: Convergence\n| N | error | time |" in chunks[0].content
    assert (
        "Table 4: Convergence (continued)\n| N | error | time |\n|---|---|---|" in chunks[1].content
    )
    carried = [line for c in chunks for line in c.content.splitlines() if line.startswith("| ")]
    assert [r for r in carried if r != "| N | error | time |"] == rows
