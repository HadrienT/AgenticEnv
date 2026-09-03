"""Orchestrates one `qm.run` invocation over the check families enabled for a mode
(WP09 §4)."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter

from corelib.ids import new_id

from qmharness.checks import convergence, cross_engine, golden, greeks, invariants, statistics
from qmharness.driver import QuantModelingClient
from qmharness.errors import CaseValidationError
from qmharness.schemas import (
    FAMILIES_BY_MODE,
    BuildFingerprint,
    CaseResult,
    CaseSpec,
    RunMode,
    RunReport,
)

_STATISTICS_KIND_HANDLERS = {
    "determinism": statistics.check_determinism,
    "ci_coverage": statistics.check_ci_coverage,
}


def _run_case(case: CaseSpec, client: QuantModelingClient, *, timeout_s: float) -> CaseResult:
    if case.family == "golden":
        return golden.check_golden(case, client, timeout_s=timeout_s)
    if case.family == "cross_engine":
        return cross_engine.check_cross_engine(case, client, timeout_s=timeout_s)
    if case.family == "invariants":
        return invariants.check_invariant(case, client, timeout_s=timeout_s)
    if case.family == "convergence":
        return convergence.check_mc_convergence(case, client, timeout_s=timeout_s)
    if case.family == "greeks":
        return greeks.check_greeks_cross_method(case, client, timeout_s=timeout_s)
    if case.family == "statistics":
        kind = case.family_params.get("kind", "determinism")
        handler = _STATISTICS_KIND_HANDLERS.get(kind)
        if handler is None:
            raise CaseValidationError(
                f"unknown statistics kind {kind!r}", details={"case_id": case.id}
            )
        return handler(case, client, timeout_s=timeout_s)
    raise CaseValidationError(f"unknown check family {case.family!r}", details={"case_id": case.id})


def run(
    cases: list[CaseSpec],
    *,
    mode: RunMode,
    client: QuantModelingClient,
    fingerprint: BuildFingerprint,
    timeout_s: float = 60.0,
) -> RunReport:
    started_at = datetime.now(UTC)
    families = FAMILIES_BY_MODE[mode]
    results: list[CaseResult] = []
    for case in cases:
        if case.family not in families:
            continue
        t0 = perf_counter()
        result = _run_case(case, client, timeout_s=timeout_s)
        result.duration_ms = int((perf_counter() - t0) * 1000)
        results.append(result)
    ended_at = datetime.now(UTC)
    summary = {
        "pass": sum(1 for r in results if r.verdict == "pass"),
        "fail": sum(1 for r in results if r.verdict == "fail"),
        "warn": sum(1 for r in results if r.verdict == "warn"),
    }
    return RunReport(
        run_id=new_id(),
        mode=mode,
        started_at=started_at,
        ended_at=ended_at,
        fingerprint=fingerprint,
        results=results,
        summary=summary,
    )
