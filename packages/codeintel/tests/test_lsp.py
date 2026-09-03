from __future__ import annotations

import sys
from pathlib import Path

import pytest
from codeintel.errors import ClangdCrashedError, ClangdNotFoundError
from codeintel.lsp import LspClient
from corelib.errors import TimeoutError_

_FIXTURE = Path(__file__).parent / "fixtures" / "fake_lsp_server.py"


def _start_fake_server(tmp_path: Path) -> LspClient:
    client = LspClient([sys.executable, str(_FIXTURE)], cwd=tmp_path)
    client.start()
    return client


def test_request_response_roundtrip(tmp_path: Path) -> None:
    client = _start_fake_server(tmp_path)
    try:
        result = client.request("echoMethod", {"foo": "bar"}, timeout_s=5.0)
        assert result == {"echo": {"foo": "bar"}}
    finally:
        client.stop()


def test_notify_does_not_block(tmp_path: Path) -> None:
    client = _start_fake_server(tmp_path)
    try:
        client.notify("initialized", {})
        result = client.request("ping", {}, timeout_s=5.0)
        assert result == {"echo": {}}
    finally:
        client.stop()


def test_error_response_raises_clangd_crashed(tmp_path: Path) -> None:
    client = _start_fake_server(tmp_path)
    try:
        with pytest.raises(ClangdCrashedError):
            client.request("boom", {}, timeout_s=5.0)
    finally:
        client.stop()


def test_timeout_raises(tmp_path: Path) -> None:
    client = _start_fake_server(tmp_path)
    try:
        with pytest.raises(TimeoutError_):
            client.request("hang", {}, timeout_s=0.2)
    finally:
        client.stop()


def test_missing_binary_raises_not_found(tmp_path: Path) -> None:
    client = LspClient(["definitely-not-a-real-binary-xyz"], cwd=tmp_path)
    with pytest.raises(ClangdNotFoundError):
        client.start()
