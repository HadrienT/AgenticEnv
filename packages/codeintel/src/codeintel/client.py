from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

from codeintel.errors import ClangdNotFoundError
from codeintel.lsp import LspClient
from codeintel.paths import to_uri

_DEFAULT_INITIALIZE_TIMEOUT_S = 30.0


class ClangdClient(Protocol):
    """Everything a `code.*` tool needs from clangd. Real production calls hit `clangd` over

    LSP (`RealClangdClient`); tests inject a fake implementing this same contract.
    """

    def open_file(self, path: Path, *, timeout_s: float) -> str:
        """Sends `textDocument/didOpen`; returns the file's `file://` URI."""
        ...

    def workspace_symbol(self, query: str, *, timeout_s: float) -> list[dict[str, Any]]: ...

    def document_symbol(self, uri: str, *, timeout_s: float) -> list[dict[str, Any]]: ...

    def definition(
        self, uri: str, line: int, column: int, *, timeout_s: float
    ) -> list[dict[str, Any]]: ...

    def hover(
        self, uri: str, line: int, column: int, *, timeout_s: float
    ) -> dict[str, Any] | None: ...

    def references(
        self, uri: str, line: int, column: int, *, timeout_s: float
    ) -> list[dict[str, Any]]: ...

    def implementation(
        self, uri: str, line: int, column: int, *, timeout_s: float
    ) -> list[dict[str, Any]]: ...

    def prepare_call_hierarchy(
        self, uri: str, line: int, column: int, *, timeout_s: float
    ) -> list[dict[str, Any]]: ...

    def incoming_calls(
        self, item: Mapping[str, Any], *, timeout_s: float
    ) -> list[dict[str, Any]]: ...

    def outgoing_calls(
        self, item: Mapping[str, Any], *, timeout_s: float
    ) -> list[dict[str, Any]]: ...

    def ast(self, uri: str, *, timeout_s: float) -> dict[str, Any] | None:
        """The `textDocument/ast` clangd extension, for the whole file."""
        ...


class RealClangdClient:
    """Wraps `LspClient` with clangd's `initialize` handshake and per-tool LSP methods."""

    def __init__(self, lsp: LspClient, *, root: Path) -> None:
        self._lsp = lsp
        self._root = root
        self._opened: set[str] = set()

    def initialize(self, *, compile_commands_dir: Path, timeout_s: float) -> None:
        params: dict[str, Any] = {
            "processId": None,
            "rootUri": to_uri(self._root),
            "capabilities": {
                "offsetEncoding": ["utf-8", "utf-16"],
                "textDocument": {
                    "references": {"container": True},
                    "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                },
            },
            "initializationOptions": {
                "compilationDatabasePath": str(compile_commands_dir),
            },
        }
        self._lsp.request("initialize", params, timeout_s=timeout_s)
        self._lsp.notify("initialized", {})

    def shutdown(self, *, timeout_s: float) -> None:
        self._lsp.request("shutdown", {}, timeout_s=timeout_s)
        self._lsp.notify("exit", {})

    def open_file(self, path: Path, *, timeout_s: float) -> str:
        uri = to_uri(path)
        if uri not in self._opened:
            text = path.read_text(encoding="utf-8")
            self._lsp.notify(
                "textDocument/didOpen",
                {"textDocument": {"uri": uri, "languageId": "cpp", "version": 1, "text": text}},
            )
            self._opened.add(uri)
        return uri

    def workspace_symbol(self, query: str, *, timeout_s: float) -> list[dict[str, Any]]:
        result = self._lsp.request("workspace/symbol", {"query": query}, timeout_s=timeout_s)
        return list(result) if result else []

    def document_symbol(self, uri: str, *, timeout_s: float) -> list[dict[str, Any]]:
        result = self._lsp.request(
            "textDocument/documentSymbol", {"textDocument": {"uri": uri}}, timeout_s=timeout_s
        )
        return list(result) if result else []

    def definition(
        self, uri: str, line: int, column: int, *, timeout_s: float
    ) -> list[dict[str, Any]]:
        result = self._lsp.request(
            "textDocument/definition",
            {"textDocument": {"uri": uri}, "position": {"line": line, "character": column}},
            timeout_s=timeout_s,
        )
        return _as_list(result)

    def hover(self, uri: str, line: int, column: int, *, timeout_s: float) -> dict[str, Any] | None:
        result = self._lsp.request(
            "textDocument/hover",
            {"textDocument": {"uri": uri}, "position": {"line": line, "character": column}},
            timeout_s=timeout_s,
        )
        return dict(result) if result else None

    def references(
        self, uri: str, line: int, column: int, *, timeout_s: float
    ) -> list[dict[str, Any]]:
        result = self._lsp.request(
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
                "context": {"includeDeclaration": False},
            },
            timeout_s=timeout_s,
        )
        return list(result) if result else []

    def implementation(
        self, uri: str, line: int, column: int, *, timeout_s: float
    ) -> list[dict[str, Any]]:
        result = self._lsp.request(
            "textDocument/implementation",
            {"textDocument": {"uri": uri}, "position": {"line": line, "character": column}},
            timeout_s=timeout_s,
        )
        return _as_list(result)

    def prepare_call_hierarchy(
        self, uri: str, line: int, column: int, *, timeout_s: float
    ) -> list[dict[str, Any]]:
        result = self._lsp.request(
            "textDocument/prepareCallHierarchy",
            {"textDocument": {"uri": uri}, "position": {"line": line, "character": column}},
            timeout_s=timeout_s,
        )
        return list(result) if result else []

    def incoming_calls(self, item: Mapping[str, Any], *, timeout_s: float) -> list[dict[str, Any]]:
        result = self._lsp.request(
            "callHierarchy/incomingCalls", {"item": item}, timeout_s=timeout_s
        )
        return list(result) if result else []

    def outgoing_calls(self, item: Mapping[str, Any], *, timeout_s: float) -> list[dict[str, Any]]:
        result = self._lsp.request(
            "callHierarchy/outgoingCalls", {"item": item}, timeout_s=timeout_s
        )
        return list(result) if result else []

    def ast(self, uri: str, *, timeout_s: float) -> dict[str, Any] | None:
        result = self._lsp.request(
            "textDocument/ast",
            {
                "textDocument": {"uri": uri},
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 1_000_000, "character": 0},
                },
            },
            timeout_s=timeout_s,
        )
        return dict(result) if result else None


def _as_list(result: Any) -> list[dict[str, Any]]:
    """`textDocument/definition`/`implementation` may return one `Location` or a list."""
    if result is None:
        return []
    if isinstance(result, list):
        return list(result)
    return [result]


class ClangdSession:
    """Owns one `clangd` subprocess for the lifetime of a single tool call.

    The on-disk background index (`.cache/clangd/index/` next to `compile_commands.json`) is
    what makes this cheap across calls (I1/I2): clangd re-reads cached `*.idx` shards instead
    of reparsing the whole project every time.
    """

    def __init__(
        self,
        root: Path,
        compile_commands_dir: Path,
        *,
        clangd_path: str = "clangd",
        extra_args: Sequence[str] = (),
    ) -> None:
        if shutil.which(clangd_path) is None:
            raise ClangdNotFoundError(
                f"clangd not found on PATH: {clangd_path}", details={"binary": clangd_path}
            )
        self._root = root
        self._compile_commands_dir = compile_commands_dir
        self._lsp = LspClient(["clangd", "--background-index", *extra_args], cwd=root)
        self._client = RealClangdClient(self._lsp, root=root)

    def __enter__(self) -> ClangdClient:
        self._lsp.start()
        self._client.initialize(
            compile_commands_dir=self._compile_commands_dir,
            timeout_s=_DEFAULT_INITIALIZE_TIMEOUT_S,
        )
        return self._client

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            self._client.shutdown(timeout_s=5.0)
        except Exception:  # noqa: BLE001 - best-effort cleanup, never mask the real error
            pass
        finally:
            self._lsp.stop()
