from __future__ import annotations

from pathlib import Path

from cppdev.diagnostics import parse_compiler_output

FIXTURES = Path(__file__).parent / "fixtures"


def test_gcc_template_instantiation_trace_is_folded_to_a_counter() -> None:
    raw = (FIXTURES / "gcc_template_trace.txt").read_text(encoding="utf-8")

    report = parse_compiler_output(raw, workspace_root=Path("/workspace"))

    assert report.summary.errors == 1
    assert len(report.errors) == 1
    diagnostic = report.errors[0]
    assert diagnostic.severity == "error"
    assert diagnostic.file == "include/quantModeling/utils/vector_ops.hpp"
    assert diagnostic.line == 15
    assert diagnostic.column == 12
    # two folded lines: "In instantiation of..." + "required from here"
    assert diagnostic.template_trace_omitted == 2


def test_clang_candidate_notes_are_kept_but_instantiation_note_is_folded() -> None:
    raw = (FIXTURES / "clang_candidate_notes.txt").read_text(encoding="utf-8")

    report = parse_compiler_output(raw, workspace_root=Path("/workspace"))

    assert report.summary.errors == 1
    diagnostic = report.errors[0]
    assert len(diagnostic.related) == 2
    assert diagnostic.related[0].note.startswith("candidate function not viable")
    assert diagnostic.template_trace_omitted == 1


def test_massive_template_trace_still_produces_a_single_condensed_diagnostic() -> None:
    trace_lines = "\n".join(f"prog.cpp:{n}:1:   required from here" for n in range(200))
    raw = trace_lines + "\nprog.cpp:5:9: error: static assertion failed\n"

    report = parse_compiler_output(raw, workspace_root=Path("/workspace"))

    assert len(report.errors) == 1
    assert report.errors[0].template_trace_omitted == 200


def test_same_diagnostic_across_translation_units_is_deduplicated() -> None:
    block = "include/shared.hpp:10:3: warning: unused variable 'x' [-Wunused-variable]\n"
    raw = block * 12

    report = parse_compiler_output(raw, workspace_root=Path("/workspace"))

    assert report.summary.warnings == 1
    assert len(report.warnings) == 1
    assert report.warnings[0].occurrences == 12


def test_warnings_are_truncated_beyond_the_configured_max_but_errors_never_are() -> None:
    warnings = "\n".join(
        f"src/f{n}.cpp:{n}:1: warning: unused variable 'v{n}' [-Wunused-variable]"
        for n in range(30)
    )
    raw = warnings + "\nsrc/main.cpp:1:1: error: expected ';' before '}' token\n"

    report = parse_compiler_output(raw, workspace_root=Path("/workspace"), max_warnings=20)

    assert report.summary.errors == 1
    assert report.summary.warnings == 30
    assert len(report.errors) == 1
    assert len(report.warnings) == 20
    assert report.truncated_diagnostics == 10


def test_first_error_is_reported_in_the_summary() -> None:
    raw = (
        "src/a.cpp:1:1: warning: unused variable 'x'\n"
        "src/b.cpp:2:2: error: undeclared identifier 'y'\n"
        "src/c.cpp:3:3: error: undeclared identifier 'z'\n"
    )

    report = parse_compiler_output(raw, workspace_root=Path("/workspace"))

    assert report.summary.first_error_file == "src/b.cpp"
    assert report.summary.first_error_line == 2


def test_absolute_workspace_paths_are_relativized() -> None:
    raw = "/workspace/src/main.cpp:1:1: error: expected ';' before '}' token\n"

    report = parse_compiler_output(raw, workspace_root=Path("/workspace"))

    assert report.errors[0].file == "src/main.cpp"


def test_absolute_system_header_paths_are_left_as_is_not_a_host_leak() -> None:
    raw = "/usr/include/c++/14/vector:100:1: error: static assertion failed\n"

    report = parse_compiler_output(raw, workspace_root=Path("/workspace"))

    assert report.errors[0].file == "/usr/include/c++/14/vector"
