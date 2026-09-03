from __future__ import annotations

from pathlib import Path
from typing import Any

from cppdev.bench import run_bench as run_benchmark
from cppdev.schemas import BenchRequest

from cppdev_mcp.tools.dispatch import dispatch


def bench(
    root: str,
    binary: str,
    preset: str,
    filter: str | None = None,
    reference_path: str | None = None,
    threshold_pct: float = 10.0,
) -> dict[str, Any]:
    """Google Benchmark run vs. a reference. `threshold_pct` is a percentage, e.g. `10.0` = 10%.

    Example: `binary="build/bench/microbench", threshold_pct=10.0`.
    """

    def _run(timeout_s: int) -> dict[str, Any]:
        request = BenchRequest(
            preset=preset, filter=filter, reference_path=reference_path, threshold_pct=threshold_pct
        )
        report = run_benchmark(request, binary=Path(binary), root=Path(root), timeout_s=timeout_s)
        return report.model_dump(mode="json")

    return dispatch("cpp.bench", _run)
