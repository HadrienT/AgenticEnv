from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.definition import definition as run_definition
from codeintel.schemas import DefinitionRequest

from codeintel_mcp.tools.dispatch import dispatch


def definition(
    root: str,
    file: str,
    line: int,
    column: int,
    include_body: bool = False,
    context_lines: int = 0,
    build_dir: str = "build/dev",
) -> dict[str, Any]:
    """Signature + doc for the symbol at `file:line:column`. Set `include_body=true` for source."""

    def _run(timeout_s: int) -> dict[str, Any]:
        report = run_definition(
            DefinitionRequest(
                file=file,
                line=line,
                column=column,
                include_body=include_body,
                context_lines=context_lines,
            ),
            root=Path(root),
            compile_commands_dir=Path(root) / build_dir,
            timeout_s=float(timeout_s),
        )
        return report.model_dump(mode="json")

    return dispatch("code.definition", _run)
