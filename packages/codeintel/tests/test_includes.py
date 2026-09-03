from __future__ import annotations

from pathlib import Path

from codeintel.includes import build_includes
from codeintel.schemas import IncludesRequest


def _project(tmp_path: Path) -> Path:
    (tmp_path / "include").mkdir()
    (tmp_path / "include" / "bar.hpp").write_text("#pragma once\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.cpp").write_text(
        '#include "../include/bar.hpp"\n#include <vector>\n', encoding="utf-8"
    )
    (tmp_path / "src" / "main.cpp").write_text('#include "foo.cpp"\n', encoding="utf-8")
    return tmp_path


def test_includes_direction_lists_direct_includes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    report = build_includes(IncludesRequest(file="src/foo.cpp", direction="includes"), root=root)
    assert report.ok is True
    assert "include/bar.hpp" in report.edges
    assert "vector" in report.edges


def test_included_by_direction_finds_dependents(tmp_path: Path) -> None:
    root = _project(tmp_path)
    report = build_includes(IncludesRequest(file="src/foo.cpp", direction="included_by"), root=root)
    assert report.ok is True
    assert "src/main.cpp" in report.edges


def test_includes_max_results_truncates(tmp_path: Path) -> None:
    root = _project(tmp_path)
    report = build_includes(
        IncludesRequest(file="src/foo.cpp", direction="includes", max_results=1), root=root
    )
    assert len(report.edges) == 1
    assert report.truncated == 1
