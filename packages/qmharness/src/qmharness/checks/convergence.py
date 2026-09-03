"""WP09 §3.4: convergence. The slope is *measured* on a log-log scale, never assumed
(blueprint/10-TARGET-REPO.md rule A7).

`case.family_params` for this family:
- `sizes` (required): list of path/step counts to sweep.
- `size_field` (optional, default `n_paths`): the `case.inputs` key to override per size.
- `expected_slope` (optional, default -0.5): MC's `1/sqrt(N)` law.
- `tolerance.slope_abs` (optional, default 0.15): allowed drift from `expected_slope`.
"""

from __future__ import annotations

import math

from qmharness.driver import QuantModelingClient
from qmharness.errors import CaseValidationError
from qmharness.schemas import CaseResult, CaseSpec


def fit_loglog_slope(sizes: list[float], errors: list[float]) -> float:
    """Ordinary least squares slope of `log(error)` vs `log(size)`. Pure, no I/O."""
    if len(sizes) < 2 or len(sizes) != len(errors):
        raise CaseValidationError("need at least 2 matching (size, error) points", details={})
    xs = [math.log(s) for s in sizes]
    ys = [math.log(max(e, 1.0e-300)) for e in errors]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        raise CaseValidationError("all sizes are identical, cannot fit a slope", details={})
    return num / den


def check_mc_convergence(
    case: CaseSpec, client: QuantModelingClient, *, timeout_s: float
) -> CaseResult:
    if case.expected is None or "price" not in case.expected:
        raise CaseValidationError(
            f"convergence case {case.id!r} needs expected.price as the reference",
            details={"case_id": case.id},
        )
    reference = case.expected["price"]
    size_field = case.family_params.get("size_field", "n_paths")
    sizes = [float(n) for n in case.family_params["sizes"]]

    observed: dict[str, float] = {}
    errors: list[float] = []
    for size in sizes:
        variant = case.model_copy(update={"inputs": {**case.inputs, size_field: size}})
        outcome = client.price(variant, timeout_s=timeout_s)
        error = abs(outcome.price - reference)
        errors.append(error)
        observed[f"error_at_{int(size)}"] = error

    slope = fit_loglog_slope(sizes, errors)
    expected_slope = float(case.family_params.get("expected_slope", -0.5))
    slope_tol = float(case.tolerance.get("slope_abs", 0.15))
    diff = abs(slope - expected_slope)
    passed = diff <= slope_tol
    observed["slope"] = slope
    return CaseResult(
        case_id=case.id,
        family="convergence",
        verdict="pass" if passed else "fail",
        message=(
            f"slope={slope:.3f}"
            + ("" if passed else f" (expected {expected_slope} +/- {slope_tol})")
        ),
        observed=observed,
        diff_abs=diff,
    )
