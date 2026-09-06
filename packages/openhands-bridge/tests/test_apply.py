"""Unit tests for the WP08d `apply_changes` write-back logic -- pure and
Docker-free, the sandbox is a dict."""

from __future__ import annotations

import hashlib
from pathlib import Path

from openhands_bridge.apply import apply_changes, hash_host_tree
from openhands_bridge.protocol import GitChangeDTO


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sandbox(files: dict[str, bytes]):
    return lambda rel: files.get(rel)


def test_applies_added_and_updated_files(tmp_path: Path) -> None:
    (tmp_path / "keep.py").write_text("old\n")
    baseline = hash_host_tree(tmp_path, ["keep.py"])

    result, new_hashes = apply_changes(
        changes=[
            GitChangeDTO(status="UPDATED", path="keep.py"),
            GitChangeDTO(status="ADDED", path="pkg/new.py"),
        ],
        host_root=tmp_path,
        read_sandbox=_sandbox({"keep.py": b"new\n", "pkg/new.py": b"hello\n"}),
        baseline_hashes=baseline,
    )

    assert (tmp_path / "keep.py").read_bytes() == b"new\n"
    assert (tmp_path / "pkg/new.py").read_bytes() == b"hello\n"
    assert sorted(p for p, _ in result.applied) == ["keep.py", "pkg/new.py"]
    assert result.skipped == []
    assert new_hashes["keep.py"] == _sha(b"new\n")


def test_deletes_file(tmp_path: Path) -> None:
    (tmp_path / "gone.py").write_text("bye\n")
    baseline = hash_host_tree(tmp_path, ["gone.py"])

    result, new_hashes = apply_changes(
        changes=[GitChangeDTO(status="DELETED", path="gone.py")],
        host_root=tmp_path,
        read_sandbox=_sandbox({}),
        baseline_hashes=baseline,
    )

    assert not (tmp_path / "gone.py").exists()
    assert result.applied == [("gone.py", "DELETED")]
    assert "gone.py" not in new_hashes


def test_conflict_is_skipped_unless_forced(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text("v1\n")
    baseline = hash_host_tree(tmp_path, ["f.py"])
    # The user edited the host file after the session baseline was taken.
    (tmp_path / "f.py").write_text("user edit\n")

    result, _ = apply_changes(
        changes=[GitChangeDTO(status="UPDATED", path="f.py")],
        host_root=tmp_path,
        read_sandbox=_sandbox({"f.py": b"agent edit\n"}),
        baseline_hashes=baseline,
    )
    assert result.applied == []
    assert result.skipped[0][0] == "f.py"
    assert (tmp_path / "f.py").read_bytes() == b"user edit\n"

    forced, _ = apply_changes(
        changes=[GitChangeDTO(status="UPDATED", path="f.py")],
        host_root=tmp_path,
        read_sandbox=_sandbox({"f.py": b"agent edit\n"}),
        baseline_hashes=baseline,
        force=True,
    )
    assert forced.applied == [("f.py", "UPDATED")]
    assert (tmp_path / "f.py").read_bytes() == b"agent edit\n"


def test_only_paths_filters_the_change_set(tmp_path: Path) -> None:
    baseline: dict[str, str] = {}

    result, _ = apply_changes(
        changes=[
            GitChangeDTO(status="ADDED", path="a.py"),
            GitChangeDTO(status="ADDED", path="b.py"),
        ],
        host_root=tmp_path,
        read_sandbox=_sandbox({"a.py": b"a\n", "b.py": b"b\n"}),
        baseline_hashes=baseline,
        only_paths={"a.py"},
    )

    assert result.applied == [("a.py", "ADDED")]
    assert (tmp_path / "a.py").exists()
    assert not (tmp_path / "b.py").exists()


def test_path_escaping_the_workspace_is_skipped(tmp_path: Path) -> None:
    result, _ = apply_changes(
        changes=[GitChangeDTO(status="ADDED", path="../evil.py")],
        host_root=tmp_path,
        read_sandbox=_sandbox({"../evil.py": b"nope\n"}),
        baseline_hashes={},
    )

    assert result.applied == []
    assert result.skipped == [("../evil.py", "path escapes the workspace")]


def test_preserves_host_crlf_line_endings(tmp_path: Path) -> None:
    (tmp_path / "w.txt").write_bytes(b"line1\r\nline2\r\n")
    baseline = hash_host_tree(tmp_path, ["w.txt"])

    apply_changes(
        changes=[GitChangeDTO(status="UPDATED", path="w.txt")],
        host_root=tmp_path,
        read_sandbox=_sandbox({"w.txt": b"line1\nline2\nline3\n"}),
        baseline_hashes=baseline,
    )

    assert (tmp_path / "w.txt").read_bytes() == b"line1\r\nline2\r\nline3\r\n"


def test_missing_from_sandbox_is_skipped(tmp_path: Path) -> None:
    result, _ = apply_changes(
        changes=[GitChangeDTO(status="ADDED", path="ghost.py")],
        host_root=tmp_path,
        read_sandbox=_sandbox({}),
        baseline_hashes={},
    )

    assert result.applied == []
    assert result.skipped == [("ghost.py", "no longer present in the sandbox")]
