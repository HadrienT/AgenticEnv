from __future__ import annotations

import json
import shutil
from pathlib import Path

from cppdev.runner import run_command
from cppdev.schemas import BenchReport, BenchRequest, BenchResult

_DEFAULT_TIMEOUT_S = 1800
_GPU_BUSY_THRESHOLD_PCT = 5


def _gpu_is_busy(*, timeout_s: int = 10) -> bool:
    """Best-effort check: benchmarks on this box are only meaningful with `llama-server` idle."""
    if shutil.which("nvidia-smi") is None:
        return False
    result = run_command(
        ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
        cwd=Path.cwd(),
        timeout_s=timeout_s,
    )
    if result.returncode != 0:
        return False
    utilizations = [int(v) for v in result.stdout.split() if v.strip().isdigit()]
    return any(u > _GPU_BUSY_THRESHOLD_PCT for u in utilizations)


def _load_reference(reference_path: str | None) -> dict[str, float]:
    if reference_path is None:
        return {}
    path = Path(reference_path)
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {entry["name"]: float(entry["real_time"]) for entry in payload.get("benchmarks", [])}


def run_bench(
    request: BenchRequest, *, binary: Path, root: Path, timeout_s: int = _DEFAULT_TIMEOUT_S
) -> BenchReport:
    """Runs a Google Benchmark executable and flags regressions past `threshold_pct`."""
    args = [str(binary), "--benchmark_format=json"]
    if request.filter is not None:
        args.append(f"--benchmark_filter={request.filter}")
    result = run_command(args, cwd=root, timeout_s=timeout_s)
    payload = json.loads(result.stdout) if result.stdout else {"benchmarks": []}
    reference = _load_reference(request.reference_path)

    results: list[BenchResult] = []
    for entry in payload.get("benchmarks", []):
        name = entry["name"]
        time_ns = float(entry["real_time"])
        reference_ns = reference.get(name)
        regression = reference_ns is not None and time_ns > reference_ns * (
            1 + request.threshold_pct / 100
        )
        results.append(
            BenchResult(
                name=name, time_ns=time_ns, reference_ns=reference_ns, regression=regression
            )
        )

    return BenchReport(
        ok=result.returncode == 0 and not any(r.regression for r in results),
        results=results,
        llama_server_busy=_gpu_is_busy(),
    )
