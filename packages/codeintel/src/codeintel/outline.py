from __future__ import annotations

from pathlib import Path

from codeintel.client import ClangdClient
from codeintel.index import check_index_status
from codeintel.schemas import OutlineReport, OutlineRequest
from codeintel.session import resolve_client
from codeintel.symbols import to_outline_symbol


def outline(
    request: OutlineRequest,
    *,
    root: Path,
    compile_commands_dir: Path,
    timeout_s: float,
    client: ClangdClient | None = None,
) -> OutlineReport:
    """`textDocument/documentSymbol`: classes/methods/signatures, never a function body (C1)."""
    index_info = check_index_status(root, compile_commands_dir)
    with resolve_client(root, compile_commands_dir, client=client) as session:
        uri = session.open_file(root / request.file, timeout_s=timeout_s)
        raw = session.document_symbol(uri, timeout_s=timeout_s)
    symbols = [to_outline_symbol(item) for item in raw]
    return OutlineReport(ok=True, file=request.file, symbols=symbols, index=index_info)
