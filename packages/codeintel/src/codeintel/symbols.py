from __future__ import annotations

from typing import Any

from codeintel.lspkinds import symbol_kind_name
from codeintel.positions import from_lsp_position
from codeintel.schemas import OutlineSymbol


def to_outline_symbol(item: dict[str, Any]) -> OutlineSymbol:
    """Shapes one hierarchical LSP `DocumentSymbol` (C1: structure only, never a function body)."""
    start_line, _ = from_lsp_position(item["range"]["start"])
    end_line, _ = from_lsp_position(item["range"]["end"])
    children = [to_outline_symbol(child) for child in item.get("children", [])]
    return OutlineSymbol(
        name=item["name"],
        kind=symbol_kind_name(item.get("kind", 0)),
        detail=item.get("detail"),
        start_line=start_line,
        end_line=end_line,
        children=children,
    )


def find_enclosing_raw_symbol(
    items: list[dict[str, Any]], line0: int, column0: int
) -> dict[str, Any] | None:
    """Innermost raw `DocumentSymbol` (0-based LSP position) containing `(line0, column0)`."""
    best: dict[str, Any] | None = None
    for item in items:
        if _range_contains(item["range"], line0, column0):
            best = find_enclosing_raw_symbol(item.get("children", []), line0, column0) or item
    return best


def _range_contains(range_: dict[str, Any], line0: int, column0: int) -> bool:
    start, end = range_["start"], range_["end"]
    if line0 < start["line"] or line0 > end["line"]:
        return False
    if line0 == start["line"] and column0 < start["character"]:
        return False
    return not (line0 == end["line"] and column0 > end["character"])
