from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.client import ClangdClient
from codeintel.index import check_index_status
from codeintel.lspkinds import symbol_kind_name
from codeintel.paths import cap_list, from_uri, to_relative
from codeintel.positions import from_lsp_position
from codeintel.schemas import FindSymbolReport, FindSymbolRequest, Location, SymbolMatch
from codeintel.session import resolve_client


def find_symbol(
    request: FindSymbolRequest,
    *,
    root: Path,
    compile_commands_dir: Path,
    timeout_s: float,
    client: ClangdClient | None = None,
) -> FindSymbolReport:
    """`workspace/symbol`: fuzzy project-wide symbol search, `file:line` results only (C5)."""
    index_info = check_index_status(root, compile_commands_dir)
    with resolve_client(root, compile_commands_dir, client=client) as session:
        raw = session.workspace_symbol(request.query, timeout_s=timeout_s)
    matches = [_to_symbol_match(item, root) for item in raw]
    kept, truncated = cap_list(matches, request.max_results)
    return FindSymbolReport(ok=True, matches=kept, truncated=truncated, index=index_info)


def _to_symbol_match(item: dict[str, Any], root: Path) -> SymbolMatch:
    location = item["location"]
    line, column = from_lsp_position(location["range"]["start"])
    return SymbolMatch(
        name=item["name"],
        kind=symbol_kind_name(item.get("kind", 0)),
        container=item.get("containerName"),
        location=Location(
            file=to_relative(from_uri(location["uri"]), root), line=line, column=column
        ),
    )
