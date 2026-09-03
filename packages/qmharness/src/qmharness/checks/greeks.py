"""WP09 §3.5: greeks cross-checked pathwise vs LRM vs FD vs analytic (rule A9).

`case.family_params`:
- `methods` (required): list of `case.method` variants to cross-check pairwise.
- `which` (optional, default `["delta"]`): greek names to compute.
"""

from __future__ import annotations

from qmharness.driver import QuantModelingClient
from qmharness.errors import CaseValidationError
from qmharness.schemas import CaseResult, CaseSpec, GreeksOutcome


def max_pairwise_rel_diff(values_by_method: dict[str, dict[str, float]]) -> dict[str, float]:
    """For each greek name, the largest relative difference across all method pairs.
    Pure, no I/O — unit-testable directly."""
    methods = list(values_by_method)
    if len(methods) < 2:
        raise CaseValidationError("need at least 2 methods to cross-check", details={})
    greek_names: set[str] = set()
    for values in values_by_method.values():
        greek_names.update(values)
    result: dict[str, float] = {}
    for greek in greek_names:
        worst = 0.0
        for i, m1 in enumerate(methods):
            for m2 in methods[i + 1 :]:
                v1 = values_by_method[m1].get(greek)
                v2 = values_by_method[m2].get(greek)
                if v1 is None or v2 is None:
                    continue
                denom = max(abs(v1), abs(v2), 1.0e-12)
                worst = max(worst, abs(v1 - v2) / denom)
        result[greek] = worst
    return result


def check_greeks_cross_method(
    case: CaseSpec, client: QuantModelingClient, *, timeout_s: float
) -> CaseResult:
    methods = case.family_params.get("methods")
    which = case.family_params.get("which", ["delta"])
    if not methods:
        raise CaseValidationError(
            f"greeks case {case.id!r} needs family_params.methods", details={"case_id": case.id}
        )
    tol_rel = float(case.tolerance.get("rel", 1.0e-2))

    values_by_method: dict[str, dict[str, float]] = {}
    for method in methods:
        variant = case.model_copy(update={"method": method})
        outcome: GreeksOutcome = client.greeks(variant, which, timeout_s=timeout_s)
        values_by_method[method] = outcome.values

    worst_by_greek = max_pairwise_rel_diff(values_by_method)
    worst = max(worst_by_greek.values())
    passed = worst <= tol_rel
    observed = {
        f"{method}_{greek}": values_by_method[method][greek]
        for method in methods
        for greek in which
        if greek in values_by_method[method]
    }
    return CaseResult(
        case_id=case.id,
        family="greeks",
        verdict="pass" if passed else "fail",
        message=(
            "within tolerance"
            if passed
            else f"worst pairwise relative diff {worst:.3e} exceeds {tol_rel:.3e}"
        ),
        observed=observed,
        diff_rel=worst,
    )
