from __future__ import annotations

import contextlib
import json
import subprocess
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from queue import Empty, Queue
from typing import IO, Any

from corelib.errors import TimeoutError_

from codeintel.errors import ClangdCrashedError, ClangdNotFoundError

_ENCODING = "utf-8"


def _read_headers(stream: IO[bytes]) -> dict[str, str] | None:
    """Reads one `Content-Length: N\\r\\n\\r\\n`-style header block; `None` at end of stream."""
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        text = line.decode("ascii", errors="replace").strip("\r\n")
        if text == "":
            return headers
        key, _, value = text.partition(":")
        headers[key.strip()] = value.strip()


class LspClient:
    """Generic JSON-RPC/LSP transport over stdio. No knowledge of clangd-specific methods."""

    def __init__(self, args: Sequence[str], *, cwd: Path) -> None:
        self._args = list(args)
        self._cwd = cwd
        self._process: subprocess.Popen[bytes] | None = None
        self._next_id = 1
        self._lock = threading.Lock()
        self._pending: dict[int, Queue[Mapping[str, Any]]] = {}
        self._reader_thread: threading.Thread | None = None
        self._stopped = threading.Event()

    def start(self) -> None:
        """Spawns the language server. Raises `ClangdNotFoundError` if the binary is missing."""
        try:
            self._process = subprocess.Popen(  # noqa: S603 - fixed arg list, never shell text
                self._args,
                cwd=self._cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise ClangdNotFoundError(
                f"language server binary not found: {self._args[0]}",
                details={"binary": self._args[0]},
            ) from exc
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def _read_loop(self) -> None:
        assert self._process is not None
        stream = self._process.stdout
        assert stream is not None
        while not self._stopped.is_set():
            headers = _read_headers(stream)
            if headers is None:
                return
            length = headers.get("Content-Length")
            if length is None:
                continue
            body = stream.read(int(length))
            if not body:
                return
            try:
                message = json.loads(body.decode(_ENCODING))
            except json.JSONDecodeError:
                continue
            self._dispatch(message)

    def _dispatch(self, message: Mapping[str, Any]) -> None:
        if "id" in message and ("result" in message or "error" in message):
            with self._lock:
                queue = self._pending.pop(message["id"], None)
            if queue is not None:
                queue.put(message)
        # Server->client requests/notifications (e.g. `window/logMessage`) are intentionally
        # dropped: this client only ever waits on request/response pairs it initiated.

    def request(self, method: str, params: Mapping[str, Any], *, timeout_s: float) -> Any:
        """Sends a request and blocks for its response. Raises `TimeoutError_` past `timeout_s`."""
        if self._process is None:
            raise ClangdCrashedError("language server not started", details={"method": method})
        with self._lock:
            msg_id = self._next_id
            self._next_id += 1
            queue: Queue[Mapping[str, Any]] = Queue(maxsize=1)
            self._pending[msg_id] = queue
        self._write({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        try:
            message = queue.get(timeout=timeout_s)
        except Empty as exc:
            with self._lock:
                self._pending.pop(msg_id, None)
            raise TimeoutError_(
                f"language server did not answer {method!r} within {timeout_s}s",
                details={"method": method, "timeout_s": timeout_s},
            ) from exc
        if "error" in message:
            error = message["error"]
            raise ClangdCrashedError(
                f"language server returned an error for {method!r}: {error.get('message')}",
                details={"method": method, "code": error.get("code")},
            )
        return message.get("result")

    def notify(self, method: str, params: Mapping[str, Any]) -> None:
        """Fire-and-forget message (e.g. `textDocument/didOpen`, `initialized`)."""
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _write(self, message: Mapping[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise ClangdCrashedError("language server not started", details={})
        encoded = json.dumps(message).encode(_ENCODING)
        header = f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii")
        try:
            self._process.stdin.write(header + encoded)
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ClangdCrashedError(
                "language server process closed its stdin", details={}
            ) from exc

    def stop(self) -> None:
        """Closes stdin and waits briefly for a clean exit before killing the process."""
        self._stopped.set()
        if self._process is not None:
            if self._process.stdin is not None:
                with contextlib.suppress(OSError):
                    self._process.stdin.close()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2)
