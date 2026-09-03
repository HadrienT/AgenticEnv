from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from cppdev.sanitize import run_sanitize as run_sanitizer
from cppdev.schemas import SanitizeRequest

from cppdev_mcp.tools.dispatch import dispatch


def sanitize(
    root: str,
    build_dir: str,
    preset: Literal["asan", "ubsan"],
    target: str,
    args: list[str] | None = None,
) -> dict[str, Any]:
    """Run an ASan/UBSan build's binary. `preset` is `"asan"` or `"ubsan"`, not a time unit.

    Example: `preset="asan", target="hello", build_dir="build/asan"`.
    """

    def _run(timeout_s: int) -> dict[str, Any]:
        request = SanitizeRequest(preset=preset, target=target, args=args or [])
        report = run_sanitizer(
            request, build_dir=Path(build_dir), root=Path(root), timeout_s=timeout_s
        )
        return report.model_dump(mode="json")

    return dispatch("cpp.sanitize", _run)
