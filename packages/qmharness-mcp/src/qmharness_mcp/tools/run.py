from __future__ import annotations

from pathlib import Path
from typing import Any

from corelib.config import load_yaml_config
from qmharness.config import QmharnessConfig
from qmharness.schemas import RunMode
from qmharness.session import run_build

from qmharness_mcp.tools.dispatch import dispatch


def run(
    root: str,
    mode: RunMode = "quick",
    build_dir: str | None = None,
    preset: str | None = None,
    golden_dir: str | None = None,
    persist: bool = False,
) -> dict[str, Any]:
    """Runs the check families enabled for `mode` (quick/standard/full) against the
    build under `root`/`build_dir` and returns the aggregated `RunReport`."""

    def _run(timeout_s: int) -> dict[str, Any]:
        config = load_yaml_config("qmharness.yaml", QmharnessConfig)
        report = run_build(
            Path(root),
            config=config,
            mode=mode,
            timeout_s=float(timeout_s),
            build_dir=build_dir,
            preset=preset,
            golden_dir=golden_dir,
        )
        if persist:
            from qmharness.store import record_run

            record_run(report)
        return report.model_dump(mode="json")

    return dispatch("qm.run", _run)
