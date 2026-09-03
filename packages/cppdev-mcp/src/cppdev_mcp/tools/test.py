from __future__ import annotations

from pathlib import Path
from typing import Any

from cppdev.schemas import TestRequest
from cppdev.test import run_tests as run_ctest

from cppdev_mcp.tools.dispatch import dispatch


def test(
    root: str,
    preset: str,
    build_dir: str,
    filter: str | None = None,
    label: str | None = None,
    jobs: int | None = None,
) -> dict[str, Any]:
    """Run `ctest` against an already-configured build. `jobs` is a parallelism count.

    Example: `preset="dev", build_dir="build/dev", filter="hello_runs"`.
    """

    def _run(timeout_s: int) -> dict[str, Any]:
        request = TestRequest(preset=preset, filter=filter, label=label, jobs=jobs)
        report = run_ctest(request, build_dir=Path(build_dir), timeout_s=timeout_s)
        return report.model_dump(mode="json")

    return dispatch("cpp.test", _run)
