from __future__ import annotations

from pathlib import Path
from typing import Any

from cppdev.analyze import run_tidy as run_clang_tidy
from cppdev.schemas import TidyRequest

from cppdev_mcp.tools.dispatch import dispatch


def tidy(root: str, paths: list[str], build_dir: str, checks: str | None = None) -> dict[str, Any]:
    """`clang-tidy` static analysis. Example: `paths=["src/main.cpp"], build_dir="build/dev"`."""

    def _run(timeout_s: int) -> dict[str, Any]:
        request = TidyRequest(paths=paths, build_dir=build_dir, checks=checks)
        report = run_clang_tidy(request, root=Path(root), timeout_s=timeout_s)
        return report.model_dump(mode="json")

    return dispatch("cpp.tidy", _run)
