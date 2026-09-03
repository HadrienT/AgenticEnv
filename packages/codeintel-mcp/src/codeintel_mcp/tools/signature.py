from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.schemas import SignatureRequest
from codeintel.signature import signature as run_signature

from codeintel_mcp.tools.dispatch import dispatch


def signature(
    root: str, file: str, line: int, column: int, build_dir: str = "build/dev"
) -> dict[str, Any]:
    """The exact signature of the symbol at `file:line:column`, without reading the file."""

    def _run(timeout_s: int) -> dict[str, Any]:
        report = run_signature(
            SignatureRequest(file=file, line=line, column=column),
            root=Path(root),
            compile_commands_dir=Path(root) / build_dir,
            timeout_s=float(timeout_s),
        )
        return report.model_dump(mode="json")

    return dispatch("code.signature", _run)
