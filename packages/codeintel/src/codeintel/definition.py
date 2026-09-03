from __future__ import annotations

from pathlib import Path

from codeintel.client import ClangdClient
from codeintel.hovertext import hover_to_signature_and_doc
from codeintel.index import check_index_status
from codeintel.paths import extract_context, from_uri, to_relative
from codeintel.positions import from_lsp_position, to_lsp_position
from codeintel.schemas import CodeSnippet, DefinitionReport, DefinitionRequest, Location
from codeintel.session import resolve_client


def definition(
    request: DefinitionRequest,
    *,
    root: Path,
    compile_commands_dir: Path,
    timeout_s: float,
    client: ClangdClient | None = None,
) -> DefinitionReport:
    """C2: signature + doc by default. `include_body=True` is required to get source text."""
    index_info = check_index_status(root, compile_commands_dir)
    with resolve_client(root, compile_commands_dir, client=client) as session:
        uri = session.open_file(root / request.file, timeout_s=timeout_s)
        position = to_lsp_position(request.line, request.column)
        raw = session.definition(uri, position["line"], position["character"], timeout_s=timeout_s)
        if not raw:
            return DefinitionReport(ok=False, index=index_info)
        target = raw[0]
        target_uri = target.get("uri") or target["targetUri"]
        target_range = target.get("range") or target["targetSelectionRange"]
        target_path = from_uri(target_uri)
        def_uri = session.open_file(target_path, timeout_s=timeout_s)
        hover = session.hover(
            def_uri,
            target_range["start"]["line"],
            target_range["start"]["character"],
            timeout_s=timeout_s,
        )
    line, column = from_lsp_position(target_range["start"])
    signature, documentation = hover_to_signature_and_doc(hover)
    body = (
        _extract_body(target_path, root, line, request.context_lines)
        if request.include_body
        else None
    )
    return DefinitionReport(
        ok=True,
        location=Location(file=to_relative(target_path, root), line=line, column=column),
        signature=signature,
        documentation=documentation,
        body=body,
        index=index_info,
    )


def _extract_body(path: Path, root: Path, line: int, context_lines: int) -> CodeSnippet:
    lines = path.read_text(encoding="utf-8").splitlines()
    before, after = extract_context(lines, line, context_lines)
    start_line = line - len(before)
    end_line = line + len(after)
    excerpt = "\n".join([*before, lines[line - 1], *after])
    return CodeSnippet(
        file=to_relative(path, root), start_line=start_line, end_line=end_line, text=excerpt
    )
