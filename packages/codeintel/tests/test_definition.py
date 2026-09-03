from __future__ import annotations

from pathlib import Path

from codeintel.definition import definition
from codeintel.schemas import DefinitionRequest


def test_definition_not_found(cpp_project: Path, fake_client) -> None:
    fake_client.definition_result = []
    report = definition(
        DefinitionRequest(file="src/foo.cpp", line=4, column=12),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.ok is False
    assert report.location is None


def test_definition_returns_signature_and_doc(cpp_project: Path, fake_client) -> None:
    file_uri = (cpp_project / "src" / "foo.cpp").resolve().as_uri()
    fake_client.definition_result = [
        {
            "uri": file_uri,
            "range": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 10}},
        }
    ]
    fake_client.hover_result = {"contents": {"value": "```cpp\nint helper()\n```\nHelper doc."}}
    report = definition(
        DefinitionRequest(file="src/foo.cpp", line=4, column=12),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.ok is True
    assert report.location is not None
    assert report.location.file == "src/foo.cpp"
    assert report.location.line == 1
    assert report.signature == "int helper()"
    assert report.documentation == "Helper doc."
    assert report.body is None


def test_definition_includes_body_when_requested(cpp_project: Path, fake_client) -> None:
    file_uri = (cpp_project / "src" / "foo.cpp").resolve().as_uri()
    fake_client.definition_result = [
        {
            "uri": file_uri,
            "range": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 10}},
        }
    ]
    fake_client.hover_result = None
    report = definition(
        DefinitionRequest(
            file="src/foo.cpp", line=4, column=12, include_body=True, context_lines=1
        ),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.body is not None
    assert report.body.file == "src/foo.cpp"
    assert "helper" in report.body.text
