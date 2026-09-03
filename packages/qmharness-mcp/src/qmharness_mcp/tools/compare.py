from __future__ import annotations

from pathlib import Path
from typing import Any

from qmharness.compare import compare_builds
from qmharness.schemas import RunReport

from qmharness_mcp.tools.dispatch import dispatch


def _load_report(report_path: str | None, run_id: str | None) -> RunReport:
    if report_path is not None:
        return RunReport.model_validate_json(Path(report_path).read_text(encoding="utf-8"))
    if run_id is not None:
        from qmharness.store import get_run

        return get_run(run_id)
    raise ValueError("need either a *_report path or a *_run_id")


def compare(
    baseline_report: str | None = None,
    baseline_run_id: str | None = None,
    candidate_report: str | None = None,
    candidate_run_id: str | None = None,
) -> dict[str, Any]:
    """Diffs two already-produced `RunReport`s (by file path or stored run id) and refuses
    the comparison outright if the two builds aren't comparable (WP09 §5, §8). Rebuilding
    at an arbitrary git ref is `cpp.build`'s job, not this tool's -- run `qm.run --persist`
    at each ref first, then compare the two resulting reports/run ids."""

    def _run(timeout_s: int) -> dict[str, Any]:
        baseline = _load_report(baseline_report, baseline_run_id)
        candidate = _load_report(candidate_report, candidate_run_id)
        report = compare_builds(baseline, candidate)
        return report.model_dump(mode="json")

    return dispatch("qm.compare", _run)
