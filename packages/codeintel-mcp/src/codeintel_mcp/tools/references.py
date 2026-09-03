from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.references import references as run_references
from codeintel.schemas import ReferencesRequest

from codeintel_mcp.tools.dispatch import dispatch


def references(
    root: str,
    file: str,
    line: int,
    column: int,
    max_results: int = 200,
    build_dir: str = "build/dev",
) -> dict[str, Any]:
    """Every call/use site of the symbol at `file:line:column`. Exhaustive; see `total_found`."""

    def _run(timeout_s: int) -> dict[str, Any]:
        report = run_references(
            ReferencesRequest(file=file, line=line, column=column, max_results=max_results),
            root=Path(root),
            compile_commands_dir=Path(root) / build_dir,
            timeout_s=float(timeout_s),
        )
        return report.model_dump(mode="json")

    return dispatch("code.references", _run)
