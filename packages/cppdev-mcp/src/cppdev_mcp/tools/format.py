from __future__ import annotations

from pathlib import Path
from typing import Any

from cppdev.format import check_format
from cppdev.schemas import FormatRequest

from cppdev_mcp.tools.dispatch import dispatch


def format_check(root: str, paths: list[str]) -> dict[str, Any]:
    """`clang-format --dry-run` check, never rewrites files. Example: `paths=["src/main.cpp"]`."""

    def _run(timeout_s: int) -> dict[str, Any]:
        report = check_format(FormatRequest(paths=paths), root=Path(root), timeout_s=timeout_s)
        return report.model_dump(mode="json")

    return dispatch("cpp.format_check", _run)
