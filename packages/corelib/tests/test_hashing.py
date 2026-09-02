from __future__ import annotations

from pathlib import Path

from corelib.hashing import args_sha, sha256_file, sha256_obj


def test_sha256_file_matches_known_digest(tmp_path: Path) -> None:
    path = tmp_path / "data.bin"
    path.write_bytes(b"hello world")
    # sha256("hello world")
    assert sha256_file(path) == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_sha256_obj_is_order_independent() -> None:
    assert sha256_obj({"a": 1, "b": 2}) == sha256_obj({"b": 2, "a": 1})


def test_sha256_obj_is_deterministic() -> None:
    assert sha256_obj({"x": [1, 2, 3]}) == sha256_obj({"x": [1, 2, 3]})


def test_args_sha_is_alias_of_sha256_obj() -> None:
    payload = {"tool": "kb.search", "k": 8}
    assert args_sha(payload) == sha256_obj(payload)
