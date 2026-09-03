from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.outline import outline as run_outline
from codeintel.schemas import OutlineRequest

from codeintel_mcp.tools.dispatch import dispatch


def outline(root: str, file: str, build_dir: str = "build/dev") -> dict[str, Any]:
    """Classes/methods/signatures of `file`, never function bodies (C1)."""

    def _run(timeout_s: int) -> dict[str, Any]:
        report = run_outline(
            OutlineRequest(file=file),
            root=Path(root),
            compile_commands_dir=Path(root) / build_dir,
            timeout_s=float(timeout_s),
        )
        return report.model_dump(mode="json")

    return dispatch("code.outline", _run)
