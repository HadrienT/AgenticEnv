from __future__ import annotations

import subprocess
from pathlib import Path

from codeintel.diff_context import diff_context
from codeintel.schemas import DiffContextRequest


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _git_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    file_path = tmp_path / "src" / "foo.cpp"
    file_path.write_text("int foo() {\n    return 1;\n}\n", encoding="utf-8")
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "test@example.com"], tmp_path)
    _git(["config", "user.name", "Test"], tmp_path)
    _git(["add", "."], tmp_path)
    _git(["commit", "-q", "-m", "base"], tmp_path)
    file_path.write_text("int foo() {\n    return 2;\n}\n", encoding="utf-8")
    _git(["commit", "-q", "-am", "head"], tmp_path)
    return tmp_path


def test_diff_context_finds_impacted_symbol(tmp_path: Path, fake_client) -> None:
    root = _git_project(tmp_path)
    (root / "build").mkdir()
    (root / "build" / "compile_commands.json").write_text("[]", encoding="utf-8")
    fake_client.document_symbol_result = [
        {
            "name": "foo",
            "kind": 12,
            "detail": None,
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 2, "character": 1}},
            "selectionRange": {
                "start": {"line": 0, "character": 4},
                "end": {"line": 0, "character": 7},
            },
            "children": [],
        }
    ]
    fake_client.references_result = [
        {"uri": "file:///dummy", "range": {"start": {"line": 0, "character": 0}}}
    ]
    report = diff_context(
        DiffContextRequest(base_ref="HEAD~1", head_ref="HEAD"),
        root=root,
        compile_commands_dir=root / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.ok is True
    assert len(report.impacted) == 1
    assert report.impacted[0].name == "foo"
    assert report.impacted[0].references_count == 1
