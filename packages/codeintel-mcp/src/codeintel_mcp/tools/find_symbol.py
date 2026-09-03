from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.find_symbol import find_symbol as run_find_symbol
from codeintel.schemas import FindSymbolRequest

from codeintel_mcp.tools.dispatch import dispatch


def find_symbol(
    root: str, query: str, max_results: int = 20, build_dir: str = "build/dev"
) -> dict[str, Any]:
    """Fuzzy project-wide symbol search. Example: `query="BSEuroAsianMCEngine"`."""

    def _run(timeout_s: int) -> dict[str, Any]:
        report = run_find_symbol(
            FindSymbolRequest(query=query, max_results=max_results),
            root=Path(root),
            compile_commands_dir=Path(root) / build_dir,
            timeout_s=float(timeout_s),
        )
        return report.model_dump(mode="json")

    return dispatch("code.find_symbol", _run)
