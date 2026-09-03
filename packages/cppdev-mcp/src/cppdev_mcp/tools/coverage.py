from __future__ import annotations

from pathlib import Path
from typing import Any

from cppdev.coverage import collect_coverage
from cppdev.schemas import CoverageRequest

from cppdev_mcp.tools.dispatch import dispatch


def coverage(root: str, build_dir: str, preset: str, target: str | None = None) -> dict[str, Any]:
    """`gcovr` line/function coverage, in percent. Example: `build_dir="build/coverage"`."""

    def _run(timeout_s: int) -> dict[str, Any]:
        request = CoverageRequest(preset=preset, target=target)
        report = collect_coverage(
            request, build_dir=Path(build_dir), root=Path(root), timeout_s=timeout_s
        )
        return report.model_dump(mode="json")

    return dispatch("cpp.coverage", _run)
