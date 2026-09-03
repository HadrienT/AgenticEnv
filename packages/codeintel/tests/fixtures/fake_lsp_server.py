from __future__ import annotations

import json
import sys


def _write(message: dict) -> None:
    encoded = json.dumps(message).encode("utf-8")
    header = f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header + encoded)
    sys.stdout.buffer.flush()


def _read_message() -> dict | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        text = line.decode("ascii", errors="replace").strip("\r\n")
        if text == "":
            break
        key, _, value = text.partition(":")
        headers[key.strip()] = value.strip()
    length = int(headers["Content-Length"])
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def main() -> None:
    """A minimal fake LSP server: echoes canned responses for the requests `test_lsp.py` sends."""
    while True:
        message = _read_message()
        if message is None:
            return
        method = message.get("method")
        if "id" not in message:
            continue  # notification, no response expected
        if method == "boom":
            _write(
                {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -1, "message": "boom"}}
            )
        elif method == "hang":
            continue  # never respond, to exercise the client's timeout path
        else:
            _write(
                {"jsonrpc": "2.0", "id": message["id"], "result": {"echo": message.get("params")}}
            )


if __name__ == "__main__":
    main()
