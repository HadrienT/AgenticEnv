from __future__ import annotations

from codeintel.lspkinds import symbol_kind_name


def test_known_kinds() -> None:
    assert symbol_kind_name(5) == "class"
    assert symbol_kind_name(12) == "function"
    assert symbol_kind_name(6) == "method"


def test_unknown_kind_falls_back() -> None:
    assert symbol_kind_name(999) == "kind_999"
