from __future__ import annotations

from codeintel.symbols import find_enclosing_raw_symbol, to_outline_symbol


def _doc_symbol(name: str, kind: int, start: tuple[int, int], end: tuple[int, int], children=None):
    return {
        "name": name,
        "kind": kind,
        "detail": None,
        "range": {
            "start": {"line": start[0], "character": start[1]},
            "end": {"line": end[0], "character": end[1]},
        },
        "children": children or [],
    }


def test_to_outline_symbol_shapes_hierarchy() -> None:
    raw = _doc_symbol(
        "Foo",
        5,
        (0, 0),
        (10, 1),
        children=[_doc_symbol("bar", 6, (1, 4), (3, 5))],
    )
    outline = to_outline_symbol(raw)
    assert outline.name == "Foo"
    assert outline.kind == "class"
    assert outline.start_line == 1
    assert outline.end_line == 11
    assert len(outline.children) == 1
    assert outline.children[0].name == "bar"
    assert outline.children[0].kind == "method"


def test_find_enclosing_raw_symbol_picks_innermost() -> None:
    inner = _doc_symbol("bar", 6, (1, 0), (3, 1))
    outer = _doc_symbol("Foo", 5, (0, 0), (10, 0), children=[inner])
    found = find_enclosing_raw_symbol([outer], 2, 0)
    assert found is not None
    assert found["name"] == "bar"


def test_find_enclosing_raw_symbol_outside_any_range() -> None:
    outer = _doc_symbol("Foo", 5, (0, 0), (10, 0))
    assert find_enclosing_raw_symbol([outer], 20, 0) is None


def test_find_enclosing_raw_symbol_boundary_columns() -> None:
    outer = _doc_symbol("Foo", 5, (0, 5), (0, 10))
    assert find_enclosing_raw_symbol([outer], 0, 4) is None
    assert find_enclosing_raw_symbol([outer], 0, 5) is not None
    assert find_enclosing_raw_symbol([outer], 0, 10) is not None
    assert find_enclosing_raw_symbol([outer], 0, 11) is None
