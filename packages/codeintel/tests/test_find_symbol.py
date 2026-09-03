from __future__ import annotations

from pathlib import Path

from codeintel.find_symbol import find_symbol
from codeintel.schemas import FindSymbolRequest


def test_find_symbol_shapes_matches(cpp_project: Path, fake_client) -> None:
    file_uri = (cpp_project / "src" / "foo.cpp").resolve().as_uri()
    fake_client.workspace_symbol_result = [
        {
            "name": "foo",
            "kind": 12,
            "containerName": None,
            "location": {"uri": file_uri, "range": {"start": {"line": 2, "character": 4}}},
        }
    ]
    report = find_symbol(
        FindSymbolRequest(query="foo"),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.ok is True
    assert len(report.matches) == 1
    match = report.matches[0]
    assert match.name == "foo"
    assert match.kind == "function"
    assert match.location.file == "src/foo.cpp"
    assert match.location.line == 3
    assert match.location.column == 5


def test_find_symbol_truncates(cpp_project: Path, fake_client) -> None:
    file_uri = (cpp_project / "src" / "foo.cpp").resolve().as_uri()
    fake_client.workspace_symbol_result = [
        {
            "name": f"sym{i}",
            "kind": 12,
            "location": {"uri": file_uri, "range": {"start": {"line": 0, "character": 0}}},
        }
        for i in range(5)
    ]
    report = find_symbol(
        FindSymbolRequest(query="sym", max_results=2),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert len(report.matches) == 2
    assert report.truncated == 3
