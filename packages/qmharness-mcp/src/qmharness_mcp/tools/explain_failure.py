from __future__ import annotations

from pathlib import Path
from typing import Any

from corelib.errors import ValidationError
from qmharness.schemas import RunReport

from qmharness_mcp.tools.dispatch import dispatch


def explain_failure(
    case_id: str, report: str | None = None, run_id: str | None = None
) -> dict[str, Any]:
    """Full detail (observed/expected/diff/message) of one case, from a report file or a
    stored run id (WP09 §7)."""

    def _run(timeout_s: int) -> dict[str, Any]:
        if report is not None:
            run_report = RunReport.model_validate_json(Path(report).read_text(encoding="utf-8"))
            result = next((r for r in run_report.results if r.case_id == case_id), None)
            if result is None:
                raise ValidationError(
                    f"no result for case {case_id!r} in {report}", details={"case_id": case_id}
                )
            return result.model_dump(mode="json")
        if run_id is not None:
            from qmharness.store import get_case_result

            return get_case_result(run_id, case_id).model_dump(mode="json")
        raise ValidationError("need either report or run_id", details={})

    return dispatch("qm.explain_failure", _run)
