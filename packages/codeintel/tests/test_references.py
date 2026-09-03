from __future__ import annotations

from pathlib import Path

from codeintel.references import references
from codeintel.schemas import ReferencesRequest


def test_references_shapes_hits(cpp_project: Path, fake_client) -> None:
    file_uri = (cpp_project / "src" / "foo.cpp").resolve().as_uri()
    fake_client.references_result = [
        {"uri": file_uri, "range": {"start": {"line": 3, "character": 11}}, "containerName": "foo"}
    ]
    report = references(
        ReferencesRequest(file="src/foo.cpp", line=1, column=5),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.ok is True
    assert report.total_found == 1
    hit = report.references[0]
    assert hit.location.file == "src/foo.cpp"
    assert hit.location.line == 4
    assert hit.location.column == 12
    assert hit.container == "foo"


def test_references_truncates_but_keeps_total(cpp_project: Path, fake_client) -> None:
    file_uri = (cpp_project / "src" / "foo.cpp").resolve().as_uri()
    fake_client.references_result = [
        {"uri": file_uri, "range": {"start": {"line": i, "character": 0}}} for i in range(10)
    ]
    report = references(
        ReferencesRequest(file="src/foo.cpp", line=1, column=5, max_results=3),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.total_found == 10
    assert len(report.references) == 3
    assert report.truncated == 7
