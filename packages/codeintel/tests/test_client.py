from __future__ import annotations

import sys
from pathlib import Path

import pytest
from codeintel.client import ClangdSession, RealClangdClient, _as_list
from codeintel.errors import ClangdNotFoundError
from codeintel.lsp import LspClient

_FIXTURE = Path(__file__).parent / "fixtures" / "fake_lsp_server.py"


def _connected_client(tmp_path: Path) -> RealClangdClient:
    lsp = LspClient([sys.executable, str(_FIXTURE)], cwd=tmp_path)
    lsp.start()
    return RealClangdClient(lsp, root=tmp_path)


def test_open_file_sends_did_open_once(tmp_path: Path) -> None:
    file_path = tmp_path / "foo.cpp"
    file_path.write_text("int foo() { return 1; }\n", encoding="utf-8")
    client = _connected_client(tmp_path)
    try:
        uri1 = client.open_file(file_path, timeout_s=5.0)
        uri2 = client.open_file(file_path, timeout_s=5.0)
        assert uri1 == uri2
        assert uri1 == file_path.resolve().as_uri()
    finally:
        client._lsp.stop()


def test_hover_request_shape(tmp_path: Path) -> None:
    client = _connected_client(tmp_path)
    try:
        result = client.hover("file:///x.cpp", 3, 4, timeout_s=5.0)
        assert result == {
            "echo": {
                "textDocument": {"uri": "file:///x.cpp"},
                "position": {"line": 3, "character": 4},
            }
        }
    finally:
        client._lsp.stop()


def test_as_list_normalizes_single_and_list_and_none() -> None:
    assert _as_list(None) == []
    assert _as_list({"a": 1}) == [{"a": 1}]
    assert _as_list([{"a": 1}, {"b": 2}]) == [{"a": 1}, {"b": 2}]


def test_clangd_session_raises_when_binary_missing(tmp_path: Path) -> None:
    with pytest.raises(ClangdNotFoundError):
        ClangdSession(tmp_path, tmp_path / "build", clangd_path="definitely-not-clangd-xyz")
