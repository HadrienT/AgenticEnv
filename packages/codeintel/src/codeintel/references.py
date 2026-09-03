from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.client import ClangdClient
from codeintel.index import check_index_status
from codeintel.paths import cap_list, from_uri, to_relative
from codeintel.positions import from_lsp_position, to_lsp_position
from codeintel.schemas import Location, ReferenceHit, ReferencesReport, ReferencesRequest
from codeintel.session import resolve_client


def references(
    request: ReferencesRequest,
    *,
    root: Path,
    compile_commands_dir: Path,
    timeout_s: float,
    client: ClangdClient | None = None,
) -> ReferencesReport:
    """`textDocument/references`: exhaustive on `total_found`, bounded on `references` (C3)."""
    index_info = check_index_status(root, compile_commands_dir)
    with resolve_client(root, compile_commands_dir, client=client) as session:
        uri = session.open_file(root / request.file, timeout_s=timeout_s)
        position = to_lsp_position(request.line, request.column)
        raw = session.references(uri, position["line"], position["character"], timeout_s=timeout_s)
    hits = [_to_reference_hit(item, root) for item in raw]
    kept, truncated = cap_list(hits, request.max_results)
    return ReferencesReport(
        ok=True, references=kept, total_found=len(hits), truncated=truncated, index=index_info
    )


def _to_reference_hit(item: dict[str, Any], root: Path) -> ReferenceHit:
    line, column = from_lsp_position(item["range"]["start"])
    return ReferenceHit(
        location=Location(file=to_relative(from_uri(item["uri"]), root), line=line, column=column),
        container=item.get("containerName"),
    )
