from __future__ import annotations

from pathlib import Path
from typing import Any

from cppdev.project import describe_project

from cppdev_mcp.tools.dispatch import dispatch


def targets(root: str, preset: str | None = None) -> dict[str, Any]:
    """List CMake presets, build targets, and configure state. Example: `root="/workspace/proj"`."""

    def _run(timeout_s: int) -> dict[str, Any]:
        info = describe_project(Path(root), preset=preset)
        return info.model_dump(mode="json")

    return dispatch("cpp.targets", _run)
