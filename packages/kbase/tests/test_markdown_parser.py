from __future__ import annotations

from pathlib import Path

from kbase.ingestion.parsers.markdown import MarkdownParser
from kbase.schemas import DocumentMeta


def _parse(path: Path) -> object:
    parser = MarkdownParser()
    meta = DocumentMeta(doc_key="k", title="t", doc_type="notes")
    return parser.parse(path, meta)


def test_can_parse_markdown_extensions() -> None:
    parser = MarkdownParser()
    assert parser.can_parse(Path("a.md"))
    assert parser.can_parse(Path("a.markdown"))
    assert parser.can_parse(Path("a.txt"))
    assert not parser.can_parse(Path("a.pdf"))


def test_parse_extracts_sections(documents_dir: Path) -> None:
    doc = _parse(documents_dir / "raw" / "sample-notes.md")
    titles = [s.title for s in doc.sections]
    assert titles == ["Introduction", "Volatility", "Correlation Table"]
    assert doc.sections[1].parent_id == doc.sections[0].path


def test_parse_extracts_page_numbers(documents_dir: Path) -> None:
    doc = _parse(documents_dir / "raw" / "sample-notes.md")
    assert doc.page_count == 2


def test_parse_extracts_block_equation_with_inline_number(documents_dir: Path) -> None:
    doc = _parse(documents_dir / "raw" / "sample-notes.md")
    equation_blocks = [b for b in doc.blocks if b.kind == "equation"]
    assert len(equation_blocks) == 1
    block = equation_blocks[0]
    assert block.equation is not None
    assert block.equation.equation_number == "1"
    assert "sigma" in block.equation.symbols


def test_parse_extracts_multiline_equation_with_tag(documents_dir: Path) -> None:
    doc = _parse(documents_dir / "raw" / "sample-paper.md")
    equation_blocks = [b for b in doc.blocks if b.kind == "equation"]
    assert len(equation_blocks) == 1
    block = equation_blocks[0]
    assert block.equation is not None
    assert block.equation.equation_number == "2"
    assert "tag" not in block.equation.latex


def test_parse_extracts_table_with_caption(documents_dir: Path) -> None:
    doc = _parse(documents_dir / "raw" / "sample-notes.md")
    table_blocks = [b for b in doc.blocks if b.kind == "table"]
    assert len(table_blocks) == 1
    assert table_blocks[0].table_caption == "Table: Pairwise correlations between three assets."
    assert "| A | B | C |" in (table_blocks[0].table_content_md or "")


def test_equation_is_never_split_across_blocks(documents_dir: Path) -> None:
    doc = _parse(documents_dir / "raw" / "sample-notes.md")
    equation_blocks = [b for b in doc.blocks if b.kind == "equation"]
    assert equation_blocks[0].text.count("\n") <= 1
