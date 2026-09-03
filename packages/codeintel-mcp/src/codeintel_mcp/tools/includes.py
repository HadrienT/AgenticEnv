from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.includes import build_includes
from codeintel.schemas import IncludesRequest

from codeintel_mcp.tools.dispatch import dispatch


def includes(
    root: str, file: str, direction: str = "includes", max_depth: int = 1, max_results: int = 200
) -> dict[str, Any]:
    """`#include` graph of `file`. `direction`: `"includes"` or `"included_by"`."""

    def _run(timeout_s: int) -> dict[str, Any]:
        report = build_includes(
            IncludesRequest(
                file=file,
                direction=direction,
                max_depth=max_depth,
                max_results=max_results,
            ),
            root=Path(root),
        )
        return report.model_dump(mode="json")

    return dispatch("code.includes", _run)
