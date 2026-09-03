from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.diff_context import diff_context as run_diff_context
from codeintel.schemas import DiffContextRequest

from codeintel_mcp.tools.dispatch import dispatch


def diff_context(
    root: str,
    base_ref: str,
    head_ref: str = "HEAD",
    max_results: int = 50,
    build_dir: str = "build/dev",
) -> dict[str, Any]:
    """Symbols impacted by the diff between `base_ref` and `head_ref`, with reference counts."""

    def _run(timeout_s: int) -> dict[str, Any]:
        report = run_diff_context(
            DiffContextRequest(base_ref=base_ref, head_ref=head_ref, max_results=max_results),
            root=Path(root),
            compile_commands_dir=Path(root) / build_dir,
            timeout_s=float(timeout_s),
        )
        return report.model_dump(mode="json")

    return dispatch("code.diff_context", _run)
