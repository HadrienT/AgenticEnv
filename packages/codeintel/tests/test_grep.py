from __future__ import annotations

from pathlib import Path

from codeintel.grep import grep
from codeintel.schemas import GrepRequest


def _project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.cpp").write_text(
        "int target = 1; // target in a comment\n"
        "// target on its own line\n"
        'const char* s = "target inside a string";\n'
        "int target2 = target;\n",
        encoding="utf-8",
    )
    return tmp_path


def test_grep_finds_plain_matches(tmp_path: Path) -> None:
    root = _project(tmp_path)
    report = grep(
        GrepRequest(pattern="target", exclude_comments=False, exclude_strings=False), root=root
    )
    assert report.ok is True
    assert len(report.matches) >= 4


def test_grep_excludes_comments(tmp_path: Path) -> None:
    root = _project(tmp_path)
    report = grep(
        GrepRequest(pattern="target", exclude_comments=True, exclude_strings=False), root=root
    )
    lines = {m.line for m in report.matches}
    assert 2 not in lines  # whole line is a comment


def test_grep_excludes_strings(tmp_path: Path) -> None:
    root = _project(tmp_path)
    report = grep(
        GrepRequest(pattern="target", exclude_comments=False, exclude_strings=True), root=root
    )
    for match in report.matches:
        assert match.line != 3 or "target" not in match.text.split('"')[1]


def test_grep_context_lines(tmp_path: Path) -> None:
    root = _project(tmp_path)
    report = grep(
        GrepRequest(
            pattern="target2", context_lines=1, exclude_comments=False, exclude_strings=False
        ),
        root=root,
    )
    assert len(report.matches) == 1
    match = report.matches[0]
    assert len(match.context_before) == 1
    assert match.context_after == []


def test_grep_regexp_mode(tmp_path: Path) -> None:
    root = _project(tmp_path)
    report = grep(
        GrepRequest(
            pattern=r"target\d", is_regexp=True, exclude_comments=False, exclude_strings=False
        ),
        root=root,
    )
    assert any(m.text.strip().startswith("int target2") for m in report.matches)
