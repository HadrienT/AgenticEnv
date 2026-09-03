from __future__ import annotations

from pathlib import Path

from cppdev.project import describe_project, list_presets, resolve_build_dir


def test_list_presets_reads_configure_presets_json(cmake_project: Path) -> None:
    assert list_presets(cmake_project) == ["dev"]


def test_resolve_build_dir_substitutes_source_dir_macro(cmake_project: Path) -> None:
    build_dir = resolve_build_dir(cmake_project, "dev")

    assert build_dir == cmake_project / "build" / "dev"


def test_describe_project_reports_unconfigured_before_first_configure(
    cmake_project: Path,
) -> None:
    info = describe_project(cmake_project, preset="dev")

    assert info.presets == ["dev"]
    assert info.configured is False
    assert info.targets == []
