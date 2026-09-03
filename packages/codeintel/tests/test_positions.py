from __future__ import annotations

from codeintel.positions import from_lsp_position, to_lsp_position


def test_to_lsp_position_converts_1_based_to_0_based() -> None:
    assert to_lsp_position(1, 1) == {"line": 0, "character": 0}
    assert to_lsp_position(5, 12) == {"line": 4, "character": 11}


def test_from_lsp_position_converts_0_based_to_1_based() -> None:
    assert from_lsp_position({"line": 0, "character": 0}) == (1, 1)
    assert from_lsp_position({"line": 4, "character": 11}) == (5, 12)


def test_roundtrip() -> None:
    for line, column in [(1, 1), (10, 3), (42, 7)]:
        assert from_lsp_position(to_lsp_position(line, column)) == (line, column)
