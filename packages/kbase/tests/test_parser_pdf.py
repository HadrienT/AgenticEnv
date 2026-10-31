from __future__ import annotations

import stat
from pathlib import Path

import pytest
from corelib.errors import DependencyError
from kbase.ingestion.parsers.pdf import PdfParser
from kbase.schemas import DocumentMeta

_META = DocumentMeta(doc_key="k", title="t", authors=[], doc_type="book")


def _fake_mineru(tmp_path: Path, *, produces_output: bool = True) -> Path:
    """Writes what the real one does: a `*_content_list_v2.json` under `-o`."""
    script = tmp_path / "mineru"
    body = 'mkdir -p "$4/x"; echo \'{}\' > "$4/x/a_content_list_v2.json"' if produces_output else ""
    script.write_text(f"#!/bin/bash\necho run >> {tmp_path}/calls\n{body}\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def _adapter(tmp_path: Path) -> Path:
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "Path(sys.argv[2]).write_text('<!-- page: 3 -->\\n# Title\\n\\nSome text.\\n')\n"
    )
    return adapter


def _parser(tmp_path: Path, mineru: Path) -> PdfParser:
    return PdfParser(
        mineru=mineru, adapter=_adapter(tmp_path), cache_dir=tmp_path / "cache", timeout_s=30
    )


def _pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    return pdf


def test_converts_then_parses_with_pages(tmp_path: Path) -> None:
    parsed = _parser(tmp_path, _fake_mineru(tmp_path)).parse(_pdf(tmp_path), _META)

    assert any(block.page_start == 3 for block in parsed.blocks)


def test_a_converted_file_is_never_converted_twice(tmp_path: Path) -> None:
    parser = _parser(tmp_path, _fake_mineru(tmp_path))
    pdf = _pdf(tmp_path)

    parser.parse(pdf, _META)
    parser.parse(pdf, _META)

    assert (tmp_path / "calls").read_text().count("run") == 1


def test_missing_mineru_and_missing_output_are_explicit(tmp_path: Path) -> None:
    with pytest.raises(DependencyError, match="not found"):
        _parser(tmp_path, tmp_path / "absent").parse(_pdf(tmp_path), _META)
    with pytest.raises(DependencyError, match="no content list"):
        _parser(tmp_path, _fake_mineru(tmp_path, produces_output=False)).parse(
            _pdf(tmp_path), _META
        )


def test_only_pdfs(tmp_path: Path) -> None:
    parser = _parser(tmp_path, _fake_mineru(tmp_path))

    assert parser.can_parse(Path("a.PDF"))
    assert not parser.can_parse(Path("a.md"))
