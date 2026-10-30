from __future__ import annotations

from pathlib import Path

from openhands_adapter.secret_paths import find_secret_paths

_PATTERNS = [".env", ".env.*", "!.env.example", "*.pem", "secrets"]


def test_finds_secrets_at_any_depth_and_honours_keeps(tmp_path: Path) -> None:
    (tmp_path / "svc" / "secrets").mkdir(parents=True)
    (tmp_path / "svc" / "secrets" / "db.txt").write_text("x")
    (tmp_path / ".env").write_text("x")
    (tmp_path / ".env.prod").write_text("x")
    (tmp_path / ".env.example").write_text("x")
    (tmp_path / "svc" / "tls.pem").write_text("x")
    (tmp_path / "app.py").write_text("x")

    files, dirs = find_secret_paths(tmp_path, _PATTERNS)

    assert files == [".env", ".env.prod", "svc/tls.pem"]
    assert dirs == ["svc/secrets"]


def test_skips_git_internals(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "x.pem").write_text("x")

    assert find_secret_paths(tmp_path, _PATTERNS) == ([], [])
