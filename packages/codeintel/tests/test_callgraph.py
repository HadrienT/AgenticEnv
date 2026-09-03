from __future__ import annotations

from pathlib import Path

from codeintel.callgraph import call_graph
from codeintel.schemas import CallGraphRequest


def _item(name: str, uri: str) -> dict:
    return {
        "name": name,
        "uri": uri,
        "selectionRange": {
            "start": {"line": 0, "character": 0},
            "end": {"line": 0, "character": 1},
        },
    }


def test_call_graph_no_item_found(cpp_project: Path, fake_client) -> None:
    fake_client.prepare_call_hierarchy_result = []
    report = call_graph(
        CallGraphRequest(file="src/foo.cpp", line=3, column=5, direction="callers"),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.ok is False


def test_call_graph_callers_one_level(cpp_project: Path, fake_client) -> None:
    file_uri = (cpp_project / "src" / "foo.cpp").resolve().as_uri()
    root_item = _item("foo", file_uri)
    caller_item = _item("main", file_uri)
    fake_client.prepare_call_hierarchy_result = [root_item]
    fake_client.incoming_calls_result = [{"from": caller_item}]
    report = call_graph(
        CallGraphRequest(file="src/foo.cpp", line=3, column=5, direction="callers", max_depth=2),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.ok is True
    assert report.root is not None
    assert report.root.name == "foo"
    assert len(report.root.children) == 1
    assert report.root.children[0].name == "main"


def test_call_graph_respects_max_results(cpp_project: Path, fake_client) -> None:
    file_uri = (cpp_project / "src" / "foo.cpp").resolve().as_uri()
    root_item = _item("foo", file_uri)
    fake_client.prepare_call_hierarchy_result = [root_item]
    fake_client.incoming_calls_result = [{"from": _item(f"caller{i}", file_uri)} for i in range(5)]
    report = call_graph(
        CallGraphRequest(
            file="src/foo.cpp", line=3, column=5, direction="callers", max_depth=1, max_results=2
        ),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.root is not None
    assert len(report.root.children) == 2
    assert report.truncated == 3


def test_call_graph_zero_depth_returns_leaf(cpp_project: Path, fake_client) -> None:
    file_uri = (cpp_project / "src" / "foo.cpp").resolve().as_uri()
    fake_client.prepare_call_hierarchy_result = [_item("foo", file_uri)]
    report = call_graph(
        CallGraphRequest(file="src/foo.cpp", line=3, column=5, direction="callees", max_depth=0),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.root is not None
    assert report.root.children == []
