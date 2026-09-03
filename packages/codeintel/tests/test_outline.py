from __future__ import annotations

from pathlib import Path

from codeintel.outline import outline
from codeintel.schemas import OutlineRequest


def test_outline_shapes_hierarchy(cpp_project: Path, fake_client) -> None:
    fake_client.document_symbol_result = [
        {
            "name": "Foo",
            "kind": 5,
            "detail": None,
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 10, "character": 1}},
            "children": [
                {
                    "name": "bar",
                    "kind": 6,
                    "detail": "void bar()",
                    "range": {
                        "start": {"line": 1, "character": 4},
                        "end": {"line": 3, "character": 5},
                    },
                    "children": [],
                }
            ],
        }
    ]
    report = outline(
        OutlineRequest(file="src/foo.cpp"),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.ok is True
    assert len(report.symbols) == 1
    assert report.symbols[0].name == "Foo"
    assert report.symbols[0].children[0].name == "bar"
    assert report.symbols[0].children[0].detail == "void bar()"
