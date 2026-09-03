from __future__ import annotations

from pathlib import Path

from codeintel.client import ClangdClient
from codeintel.hovertext import hover_to_signature_and_doc
from codeintel.index import check_index_status
from codeintel.positions import to_lsp_position
from codeintel.schemas import SignatureReport, SignatureRequest
from codeintel.session import resolve_client


def signature(
    request: SignatureRequest,
    *,
    root: Path,
    compile_commands_dir: Path,
    timeout_s: float,
    client: ClangdClient | None = None,
) -> SignatureReport:
    """`textDocument/hover`: the exact signature, without reading or reformatting the file."""
    index_info = check_index_status(root, compile_commands_dir)
    with resolve_client(root, compile_commands_dir, client=client) as session:
        uri = session.open_file(root / request.file, timeout_s=timeout_s)
        position = to_lsp_position(request.line, request.column)
        hover = session.hover(uri, position["line"], position["character"], timeout_s=timeout_s)
    sig, doc = hover_to_signature_and_doc(hover)
    return SignatureReport(
        ok=sig is not None or doc is not None,
        signature=sig,
        documentation=doc,
        index=index_info,
    )
