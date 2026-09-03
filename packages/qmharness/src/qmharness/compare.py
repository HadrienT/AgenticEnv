"""`qm compare`: "this refactor -- did it move a price?" (WP09 §5).

Deterministic cases (analytic/PDE/tree) and fixed-seed Monte Carlo cases are held to
zero tolerance: any nonzero drift is a regression, never absorbed as "MC noise"
without an explicit seed/path-count justification (WP09 §5's rule table).
"""

from __future__ import annotations

from qmharness.schemas import BuildFingerprint, ComparisonCaseDiff, ComparisonReport, RunReport

_FINGERPRINT_FIELDS = ("build_preset", "compiler", "compiler_version", "optimization")


def _fingerprint_mismatches(baseline: BuildFingerprint, candidate: BuildFingerprint) -> list[str]:
    return [f for f in _FINGERPRINT_FIELDS if getattr(baseline, f) != getattr(candidate, f)]


def compare_builds(
    baseline: RunReport, candidate: RunReport, *, zero_tolerance_abs: float = 1.0e-10
) -> ComparisonReport:
    mismatches = _fingerprint_mismatches(baseline.fingerprint, candidate.fingerprint)
    if mismatches:
        return ComparisonReport(
            comparable=False,
            refusal_reason=f"builds differ on: {', '.join(mismatches)}",
            baseline_fingerprint=baseline.fingerprint,
            candidate_fingerprint=candidate.fingerprint,
        )

    baseline_by_id = {r.case_id: r for r in baseline.results}
    candidate_by_id = {r.case_id: r for r in candidate.results}
    diffs: list[ComparisonCaseDiff] = []
    regressions: list[str] = []
    for case_id in sorted(set(baseline_by_id) & set(candidate_by_id)):
        b_price = baseline_by_id[case_id].observed.get("price")
        c_price = candidate_by_id[case_id].observed.get("price")
        if b_price is None or c_price is None:
            continue
        diff_abs = abs(b_price - c_price)
        diff_rel = diff_abs / abs(b_price) if b_price != 0 else diff_abs
        verdict = "pass" if diff_abs <= zero_tolerance_abs else "fail"
        note = (
            ""
            if verdict == "pass"
            else "price moved; justify by an explicit seed/path-count change or investigate"
        )
        diffs.append(
            ComparisonCaseDiff(
                case_id=case_id,
                baseline_price=b_price,
                candidate_price=c_price,
                diff_abs=diff_abs,
                diff_rel=diff_rel,
                verdict=verdict,
                note=note,
            )
        )
        if verdict == "fail":
            regressions.append(case_id)

    diffs.sort(key=lambda d: (d.verdict != "fail", d.case_id))
    return ComparisonReport(
        comparable=True,
        baseline_fingerprint=baseline.fingerprint,
        candidate_fingerprint=candidate.fingerprint,
        diffs=diffs,
        regressions=regressions,
    )
