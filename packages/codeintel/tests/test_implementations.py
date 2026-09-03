from __future__ import annotations

from pathlib import Path

from codeintel.implementations import implementations
from codeintel.schemas import ImplementationsRequest


def test_implementations_resolves_enclosing_symbol(cpp_project: Path, fake_client) -> None:
    file_uri = (cpp_project / "src" / "foo.cpp").resolve().as_uri()
    fake_client.implementation_result = [
        {
            "uri": file_uri,
            "range": {"start": {"line": 2, "character": 4}, "end": {"line": 2, "character": 7}},
        }
    ]
    fake_client.document_symbol_result = [
        {
            "name": "foo",
            "kind": 12,
            "detail": "int foo()",
            "range": {"start": {"line": 2, "character": 0}, "end": {"line": 4, "character": 1}},
            "children": [],
        }
    ]
    report = implementations(
        ImplementationsRequest(file="src/foo.cpp", line=1, column=5),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.ok is True
    assert len(report.implementations) == 1
    match = report.implementations[0]
    assert match.name == "foo"
    assert match.kind == "function"
    assert match.detail == "int foo()"


def test_implementations_no_enclosing_symbol_falls_back(cpp_project: Path, fake_client) -> None:
    file_uri = (cpp_project / "src" / "foo.cpp").resolve().as_uri()
    fake_client.implementation_result = [
        {
            "uri": file_uri,
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
        }
    ]
    fake_client.document_symbol_result = []
    report = implementations(
        ImplementationsRequest(file="src/foo.cpp", line=1, column=5),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.implementations[0].name == "?"
    assert report.implementations[0].kind == "unknown"
