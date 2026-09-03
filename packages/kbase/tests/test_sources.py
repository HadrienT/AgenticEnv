from __future__ import annotations

from pathlib import Path

import pytest
from corelib.errors import ValidationError
from kbase.ingestion import sources


def test_resolve_returns_two_documents(manifest_path: Path, documents_dir: Path) -> None:
    items = sources.resolve(manifest_path, documents_dir)
    assert {i.meta.doc_key for i in items} == {"sample-notes", "sample-paper"}
    for item in items:
        assert Path(item.resolved_path).is_file()


def test_resolve_missing_manifest_raises(documents_dir: Path) -> None:
    with pytest.raises(ValidationError):
        sources.resolve(documents_dir / "does-not-exist.yaml", documents_dir)


def test_resolve_rejects_absolute_path(tmp_path: Path, documents_dir: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "documents:\n  - doc_key: bad\n    path: /etc/passwd\n    title: t\n    doc_type: notes\n"
    )
    with pytest.raises(ValidationError):
        sources.resolve(manifest, documents_dir)


def test_resolve_rejects_path_traversal(tmp_path: Path, documents_dir: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "documents:\n"
        "  - doc_key: bad\n"
        "    path: ../../etc/passwd\n"
        "    title: t\n"
        "    doc_type: notes\n"
    )
    with pytest.raises(ValidationError):
        sources.resolve(manifest, documents_dir)


def test_resolve_path_builds_source_item(documents_dir: Path) -> None:
    items = sources.resolve_path("raw/sample-notes.md", documents_dir)
    assert len(items) == 1
    assert items[0].meta.doc_type == "notes"
