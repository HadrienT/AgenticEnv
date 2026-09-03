from __future__ import annotations

from pathlib import Path

from codeintel.paths import cap_list, extract_context, from_uri, to_relative, to_uri


def test_to_relative_inside_root() -> None:
    root = Path("/repo")
    assert to_relative(root / "src" / "foo.cpp", root) == "src/foo.cpp"


def test_to_relative_outside_root_stays_absolute() -> None:
    root = Path("/repo")
    assert to_relative("/other/foo.cpp", root) == "/other/foo.cpp"


def test_to_relative_already_relative() -> None:
    assert to_relative("src/foo.cpp", Path("/repo")) == "src/foo.cpp"


def test_uri_roundtrip(tmp_path: Path) -> None:
    file_path = tmp_path / "foo.cpp"
    file_path.write_text("", encoding="utf-8")
    assert from_uri(to_uri(file_path)) == file_path.resolve()


def test_from_uri_rejects_non_file_scheme() -> None:
    try:
        from_uri("https://example.com/foo.cpp")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_cap_list_under_limit() -> None:
    kept, truncated = cap_list([1, 2, 3], 10)
    assert kept == [1, 2, 3]
    assert truncated == 0


def test_cap_list_over_limit() -> None:
    kept, truncated = cap_list([1, 2, 3, 4, 5], 2)
    assert kept == [1, 2]
    assert truncated == 3


def test_extract_context_middle_of_file() -> None:
    lines = [f"line{i}" for i in range(1, 11)]
    before, after = extract_context(lines, 5, 2)
    assert before == ["line3", "line4"]
    assert after == ["line6", "line7"]


def test_extract_context_clamped_at_start() -> None:
    lines = [f"line{i}" for i in range(1, 6)]
    before, after = extract_context(lines, 1, 3)
    assert before == []
    assert after == ["line2", "line3", "line4"]
