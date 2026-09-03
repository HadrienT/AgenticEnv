from __future__ import annotations

from pathlib import Path

from codeintel.client import ClangdClient
from codeintel.index import check_index_status
from codeintel.lspkinds import symbol_kind_name
from codeintel.paths import cap_list, from_uri, to_relative
from codeintel.positions import from_lsp_position, to_lsp_position
from codeintel.schemas import (
    ImplementationsReport,
    ImplementationsRequest,
    Location,
    SymbolMatch,
)
from codeintel.session import resolve_client
from codeintel.symbols import find_enclosing_raw_symbol


def implementations(
    request: ImplementationsRequest,
    *,
    root: Path,
    compile_commands_dir: Path,
    timeout_s: float,
    client: ClangdClient | None = None,
) -> ImplementationsReport:
    """`textDocument/implementation`, e.g. every class deriving `IInstrumentVisitor`."""
    index_info = check_index_status(root, compile_commands_dir)
    matches: list[SymbolMatch] = []
    with resolve_client(root, compile_commands_dir, client=client) as session:
        uri = session.open_file(root / request.file, timeout_s=timeout_s)
        position = to_lsp_position(request.line, request.column)
        raw = session.implementation(
            uri, position["line"], position["character"], timeout_s=timeout_s
        )
        for location in raw:
            target_path = from_uri(location["uri"])
            target_uri = session.open_file(target_path, timeout_s=timeout_s)
            doc_symbols = session.document_symbol(target_uri, timeout_s=timeout_s)
            start = location["range"]["start"]
            symbol = find_enclosing_raw_symbol(doc_symbols, start["line"], start["character"])
            line, column = from_lsp_position(start)
            matches.append(
                SymbolMatch(
                    name=symbol["name"] if symbol else "?",
                    kind=symbol_kind_name(symbol.get("kind", 0)) if symbol else "unknown",
                    detail=symbol.get("detail") if symbol else None,
                    location=Location(
                        file=to_relative(target_path, root), line=line, column=column
                    ),
                )
            )
    kept, truncated = cap_list(matches, request.max_results)
    return ImplementationsReport(
        ok=True, implementations=kept, truncated=truncated, index=index_info
    )
