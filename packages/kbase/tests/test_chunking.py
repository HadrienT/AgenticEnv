from __future__ import annotations

from kbase.ingestion.chunking import StructuralChunker
from kbase.schemas import ChunkPolicy, ContentBlock, DocumentMeta, Equation, ParsedDocument, Section


def _doc(blocks: list[ContentBlock]) -> ParsedDocument:
    return ParsedDocument(
        meta=DocumentMeta(doc_key="k", title="t", doc_type="notes"),
        version="1",
        sha256="deadbeef",
        page_count=1,
        sections=[Section(section_id="1", parent_id=None, level=1, ordinal=1, title="S", path="1")],
        blocks=blocks,
        parser_name="markdown",
        parser_version="1",
    )


def _policy(**overrides: int) -> ChunkPolicy:
    defaults = {"target_tokens": 20, "max_tokens": 30, "overlap_tokens": 5}
    defaults.update(overrides)
    return ChunkPolicy(**defaults)


def test_short_text_block_becomes_one_chunk() -> None:
    doc = _doc([ContentBlock(kind="text", text="hello world", section_id="1")])
    chunks = StructuralChunker().chunk(doc, _policy())
    assert len(chunks) == 1
    assert chunks[0].kind == "text"
    assert chunks[0].content == "hello world"


def test_equation_block_is_atomic_and_never_split() -> None:
    equation = Equation(latex="a=b", equation_number="1", symbols=["a", "b"])
    doc = _doc(
        [
            ContentBlock(kind="text", text="before", section_id="1"),
            ContentBlock(kind="equation", text="a=b", section_id="1", equation=equation),
            ContentBlock(kind="text", text="after", section_id="1"),
        ]
    )
    chunks = StructuralChunker().chunk(doc, _policy())
    equation_chunks = [c for c in chunks if c.kind == "equation"]
    assert len(equation_chunks) == 1
    assert equation_chunks[0].content == "a=b"
    assert equation_chunks[0].has_equations is True
    assert equation_chunks[0].equation == equation


def test_table_block_is_atomic() -> None:
    doc = _doc(
        [
            ContentBlock(
                kind="table",
                text="| a | b |",
                section_id="1",
                table_caption="Table: x",
                table_content_md="| a | b |",
            )
        ]
    )
    chunks = StructuralChunker().chunk(doc, _policy())
    assert len(chunks) == 1
    assert chunks[0].kind == "table"
    assert chunks[0].table_caption == "Table: x"


def test_oversized_text_is_split_at_sentence_boundaries() -> None:
    long_text = " ".join(f"word{i}." for i in range(60))
    doc = _doc([ContentBlock(kind="text", text=long_text, section_id="1")])
    policy = _policy(target_tokens=10, max_tokens=15, overlap_tokens=2)
    chunks = StructuralChunker().chunk(doc, policy)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.n_tokens <= 15


def test_no_content_is_lost_across_chunks() -> None:
    long_text = " ".join(f"word{i}." for i in range(40))
    doc = _doc([ContentBlock(kind="text", text=long_text, section_id="1")])
    policy = _policy(target_tokens=10, max_tokens=12, overlap_tokens=0)
    chunks = StructuralChunker().chunk(doc, policy)
    joined = " ".join(c.content for c in chunks)
    for i in range(40):
        assert f"word{i}." in joined
