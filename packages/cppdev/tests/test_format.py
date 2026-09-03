from __future__ import annotations

from pathlib import Path

import cppdev.format as format_mod
import pytest
from cppdev.format import check_format
from cppdev.runner import CommandResult
from cppdev.schemas import FormatRequest


def test_check_format_flags_only_files_reported_by_clang_format(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = (
        "src/bad.cpp:10:1: warning: code should be clang-formatted [-Wclang-format-violations]\n"
    )

    def fake_run_command(args: list[str], *, cwd: Path, timeout_s: int) -> CommandResult:
        return CommandResult(
            args=tuple(args), returncode=1, stdout="", stderr=stderr, duration_ms=1
        )

    monkeypatch.setattr(format_mod, "run_command", fake_run_command)
    monkeypatch.setattr(format_mod.shutil, "which", lambda _name: "/usr/bin/clang-format")

    report = check_format(FormatRequest(paths=["src/bad.cpp", "src/good.cpp"]), root=tmp_path)

    assert report.ok is False
    assert len(report.violations) == 1
    assert report.violations[0].file == "src/bad.cpp"
    assert report.violations[0].would_reformat is True
