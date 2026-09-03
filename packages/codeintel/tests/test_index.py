from __future__ import annotations

import json
from pathlib import Path

import pytest
from codeintel.errors import IndexUnavailableError
from codeintel.index import check_index_status


def test_missing_compile_commands_raises(tmp_path: Path) -> None:
    with pytest.raises(IndexUnavailableError):
        check_index_status(tmp_path, tmp_path / "build")


def test_fresh_index_not_stale(cpp_project: Path) -> None:
    info = check_index_status(cpp_project, cpp_project / "build")
    assert info.stale is False
    assert info.warning is not None  # no background index dir yet


def test_unchanged_compile_commands_stays_fresh(cpp_project: Path) -> None:
    build_dir = cpp_project / "build"
    check_index_status(cpp_project, build_dir)
    (build_dir / ".cache" / "clangd" / "index").mkdir(parents=True)
    info = check_index_status(cpp_project, build_dir)
    assert info.stale is False
    assert info.warning is None


def test_changed_compile_commands_flagged_stale(cpp_project: Path) -> None:
    build_dir = cpp_project / "build"
    check_index_status(cpp_project, build_dir)
    (build_dir / "compile_commands.json").write_text('[{"changed": true}]', encoding="utf-8")
    info = check_index_status(cpp_project, build_dir)
    assert info.stale is True
    assert info.warning is not None


def test_meta_file_written(cpp_project: Path) -> None:
    build_dir = cpp_project / "build"
    check_index_status(cpp_project, build_dir)
    meta_path = build_dir / ".cache" / "clangd" / "agenticenv-index-meta.json"
    assert meta_path.is_file()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert "compile_commands_sha256" in meta
