from __future__ import annotations

from pathlib import Path
from typing import Any

from corelib.config import load_yaml_config
from qmharness.config import QmharnessConfig
from qmharness.driver import RealQuantModelingClient, build_fingerprint, load_quantmodeling_module
from qmharness.loader import discover_golden_files, load_cases
from qmharness.runner import run as run_harness
from qmharness.schemas import RunMode

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
        root_path = Path(root)
        resolved_build_dir = root_path / (build_dir or config.build_dir)
        resolved_preset = preset or config.build_preset
        resolved_golden_dir = root_path / (golden_dir or config.golden_dir)

        module = load_quantmodeling_module(resolved_build_dir)
        client = RealQuantModelingClient(module)
        fingerprint = build_fingerprint(root_path, resolved_build_dir, resolved_preset)
        cases = load_cases(discover_golden_files(resolved_golden_dir))
        report = run_harness(
            cases, mode=mode, client=client, fingerprint=fingerprint, timeout_s=float(timeout_s)
        )
        if persist:
            from qmharness.store import record_run

            record_run(report)
        return report.model_dump(mode="json")

    return dispatch("qm.run", _run)
