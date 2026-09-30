from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from corelib.errors import DependencyError
from openhands_adapter.session import _check_served_model


def _serve(served: list[str]) -> Iterator[str]:
    body = json.dumps({"object": "list", "data": [{"id": m} for m in served]}).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200 if self.path == "/v1/models" else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def code_server() -> Iterator[str]:
    yield from _serve(["Qwen3-Coder-30B-A3B-Instruct"])


@pytest.fixture
def translate_server() -> Iterator[str]:
    yield from _serve(["plamo-2-translate"])


def test_expected_model_passes(code_server: str) -> None:
    _check_served_model(code_server, "Qwen3-Coder-30B-A3B-Instruct")


def test_other_profile_is_refused(translate_server: str) -> None:
    with pytest.raises(DependencyError) as exc:
        _check_served_model(translate_server, "Qwen3-Coder-30B-A3B-Instruct")
    assert exc.value.details["served"] == ["plamo-2-translate"]
    assert exc.value.details["fix"] == "just llm-use code"


def test_unreachable_server_is_refused() -> None:
    with pytest.raises(DependencyError, match="not reachable"):
        _check_served_model("http://127.0.0.1:9/v1", "anything")
