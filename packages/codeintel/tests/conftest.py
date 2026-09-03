from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


class FakeClangdClient:
    """In-memory double for `ClangdClient`; tests set the `*_result` attributes directly."""

    def __init__(self) -> None:
        self.workspace_symbol_result: list[dict[str, Any]] = []
        self.document_symbol_result: list[dict[str, Any]] = []
        self.definition_result: list[dict[str, Any]] = []
        self.hover_result: dict[str, Any] | None = None
        self.references_result: list[dict[str, Any]] = []
        self.implementation_result: list[dict[str, Any]] = []
        self.prepare_call_hierarchy_result: list[dict[str, Any]] = []
        self.incoming_calls_result: list[dict[str, Any]] = []
        self.outgoing_calls_result: list[dict[str, Any]] = []
        self.ast_result: dict[str, Any] | None = None
        self.opened: list[Path] = []

    def open_file(self, path: Path, *, timeout_s: float) -> str:
        self.opened.append(path)
        return path.resolve().as_uri()

    def workspace_symbol(self, query: str, *, timeout_s: float) -> list[dict[str, Any]]:
        return self.workspace_symbol_result

    def document_symbol(self, uri: str, *, timeout_s: float) -> list[dict[str, Any]]:
        return self.document_symbol_result

    def definition(
        self, uri: str, line: int, column: int, *, timeout_s: float
    ) -> list[dict[str, Any]]:
        return self.definition_result

    def hover(self, uri: str, line: int, column: int, *, timeout_s: float) -> dict[str, Any] | None:
        return self.hover_result

    def references(
        self, uri: str, line: int, column: int, *, timeout_s: float
    ) -> list[dict[str, Any]]:
        return self.references_result

    def implementation(
        self, uri: str, line: int, column: int, *, timeout_s: float
    ) -> list[dict[str, Any]]:
        return self.implementation_result

    def prepare_call_hierarchy(
        self, uri: str, line: int, column: int, *, timeout_s: float
    ) -> list[dict[str, Any]]:
        return self.prepare_call_hierarchy_result

    def incoming_calls(self, item: dict[str, Any], *, timeout_s: float) -> list[dict[str, Any]]:
        return self.incoming_calls_result

    def outgoing_calls(self, item: dict[str, Any], *, timeout_s: float) -> list[dict[str, Any]]:
        return self.outgoing_calls_result

    def ast(self, uri: str, *, timeout_s: float) -> dict[str, Any] | None:
        return self.ast_result


@pytest.fixture
def fake_client() -> FakeClangdClient:
    return FakeClangdClient()


@pytest.fixture
def cpp_project(tmp_path: Path) -> Path:
    """A minimal fake project root: `build/compile_commands.json` + one source file."""
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "compile_commands.json").write_text("[]", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.cpp").write_text(
        "int helper() { return 1; }\n\nint foo() {\n    return helper();\n}\n",
        encoding="utf-8",
    )
    return tmp_path
