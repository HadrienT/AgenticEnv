from __future__ import annotations

from pathlib import Path

from cppdev.build import build, configure
from cppdev.project import describe_project
from cppdev.schemas import BuildRequest, ConfigureRequest


def test_configure_generates_compile_commands_and_no_diagnostics(cmake_project: Path) -> None:
    report = configure(ConfigureRequest(preset="dev"), root=cmake_project)

    assert report.ok is True
    assert report.diagnostics.summary.errors == 0
    assert Path(report.build_dir).is_dir()


def test_build_compiles_the_target_and_reports_ok(cmake_project: Path) -> None:
    configure(ConfigureRequest(preset="dev"), root=cmake_project)

    report = build(BuildRequest(preset="dev", target="hello"), root=cmake_project)

    assert report.ok is True
    assert report.diagnostics.summary.errors == 0
    assert (cmake_project / "build" / "dev" / "hello").is_file()


def test_build_surfaces_a_condensed_diagnostic_on_compile_error(cmake_project: Path) -> None:
    (cmake_project / "src" / "main.cpp").write_text(
        "int main() { return unknown_identifier; }\n", encoding="utf-8"
    )
    configure(ConfigureRequest(preset="dev"), root=cmake_project)

    report = build(BuildRequest(preset="dev", target="hello"), root=cmake_project)

    assert report.ok is False
    assert report.diagnostics.summary.errors >= 1
    assert "unknown_identifier" in report.diagnostics.errors[0].message


def test_describe_project_lists_targets_after_configure(cmake_project: Path) -> None:
    configure(ConfigureRequest(preset="dev"), root=cmake_project)

    info = describe_project(cmake_project, preset="dev")

    assert info.configured is True
    assert "hello" in info.targets
