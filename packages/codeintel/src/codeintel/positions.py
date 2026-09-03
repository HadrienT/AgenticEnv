from __future__ import annotations

from typing import TypedDict


class LspPosition(TypedDict):
    line: int
    character: int


def to_lsp_position(line: int, column: int) -> LspPosition:
    """Our API is 1-based (C5, matches compiler diagnostics); LSP positions are 0-based."""
    return {"line": line - 1, "character": column - 1}


def from_lsp_position(position: LspPosition) -> tuple[int, int]:
    """Inverse of `to_lsp_position`. Returns `(line, column)`, both 1-based."""
    return position["line"] + 1, position["character"] + 1
