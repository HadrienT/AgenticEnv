from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.implementations import implementations as run_implementations
from codeintel.schemas import ImplementationsRequest

from codeintel_mcp.tools.dispatch import dispatch


def implementations(
    root: str,
    file: str,
    line: int,
    column: int,
    max_results: int = 100,
    build_dir: str = "build/dev",
) -> dict[str, Any]:
    """Every override/derived class of the symbol at `file:line:column` (e.g. `EngineBase`)."""

    def _run(timeout_s: int) -> dict[str, Any]:
        report = run_implementations(
            ImplementationsRequest(file=file, line=line, column=column, max_results=max_results),
            root=Path(root),
            compile_commands_dir=Path(root) / build_dir,
            timeout_s=float(timeout_s),
        )
        return report.model_dump(mode="json")

    return dispatch("code.implementations", _run)
