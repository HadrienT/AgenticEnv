from __future__ import annotations

from pathlib import Path

import pytest
from codeintel.errors import ClangdNotFoundError
from codeintel.session import resolve_client


def test_resolve_client_reuses_injected_client(tmp_path: Path, fake_client) -> None:
    with resolve_client(tmp_path, tmp_path / "build", client=fake_client) as session:
        assert session is fake_client


def test_resolve_client_opens_real_session_when_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force "clangd not on PATH" regardless of whether this host happens to have it installed.
    monkeypatch.setattr("shutil.which", lambda _name: None)
    with (
        pytest.raises(ClangdNotFoundError),
        resolve_client(tmp_path, tmp_path / "build", client=None),
    ):
        pass
