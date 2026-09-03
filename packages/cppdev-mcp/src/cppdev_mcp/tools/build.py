from __future__ import annotations

from pathlib import Path
from typing import Any

from cppdev.build import build as run_build
from cppdev.build import configure as run_configure
from cppdev.schemas import BuildRequest, ConfigureRequest

from cppdev_mcp.tools.dispatch import dispatch


def configure(root: str, preset: str) -> dict[str, Any]:
    """Run `cmake --preset <preset>`. Units: none. Example: `preset="dev"`."""

    def _run(timeout_s: int) -> dict[str, Any]:
        report = run_configure(
            ConfigureRequest(preset=preset), root=Path(root), timeout_s=timeout_s
        )
        return report.model_dump(mode="json")

    return dispatch("cpp.configure", _run)


def build(
    root: str,
    preset: str,
    target: str | None = None,
    clean: bool = False,
    jobs: int | None = None,
) -> dict[str, Any]:
    """Build a target (or all). `jobs` is a parallelism count, not a time unit.

    Example: `preset="dev", target="hello"`.
    """

    def _run(timeout_s: int) -> dict[str, Any]:
        request = BuildRequest(preset=preset, target=target, clean=clean, jobs=jobs)
        report = run_build(request, root=Path(root), timeout_s=timeout_s)
        return report.model_dump(mode="json")

    return dispatch("cpp.build", _run)
