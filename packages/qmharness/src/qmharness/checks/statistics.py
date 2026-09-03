"""WP09 §3.4: statistical properties. Two checks: exact determinism (A10) and CI
coverage over repeated runs (A8, "sur K répétitions, ~95% contiennent la référence").

`case.family_params` for `check_ci_coverage`:
- `seeds` (required): one seed per repetition, baked into `case.inputs["seed"]`.
- `z` (optional, default 1.96): the CI half-width multiple (95% for a normal approx).
- `expected_coverage` (optional, default 0.95).
- `tolerance.coverage_abs` (optional, default 0.05).
"""

from __future__ import annotations

from qmharness.driver import QuantModelingClient
from qmharness.errors import CaseValidationError
from qmharness.schemas import CaseResult, CaseSpec


def coverage_fraction(
    prices: list[float], std_errors: list[float], reference: float, z: float
) -> float:
    """Fraction of repeated CIs `[price - z*se, price + z*se]` containing `reference`.
    Pure, no I/O."""
    if not prices:
        raise CaseValidationError("need at least one repetition", details={})
    hits = sum(
        1
        for price, se in zip(prices, std_errors, strict=True)
        if price - z * se <= reference <= price + z * se
    )
    return hits / len(prices)


def check_determinism(
    case: CaseSpec, client: QuantModelingClient, *, timeout_s: float
) -> CaseResult:
    """Same seed => bit-identical result (10-TARGET-REPO.md rule A10)."""
    first = client.price(case, timeout_s=timeout_s)
    second = client.price(case, timeout_s=timeout_s)
    passed = first.price == second.price
    return CaseResult(
        case_id=case.id,
        family="statistics",
        verdict="pass" if passed else "fail",
        message=(
            "bit-identical" if passed else f"{first.price!r} != {second.price!r} for the same seed"
        ),
        observed={"first": first.price, "second": second.price},
        diff_abs=abs(first.price - second.price),
    )


def check_ci_coverage(
    case: CaseSpec, client: QuantModelingClient, *, timeout_s: float
) -> CaseResult:
    if case.expected is None or "price" not in case.expected:
        raise CaseValidationError(
            f"ci_coverage case {case.id!r} needs expected.price as the reference",
            details={"case_id": case.id},
        )
    reference = case.expected["price"]
    seeds = case.family_params["seeds"]
    z = float(case.family_params.get("z", 1.96))
    expected_coverage = float(case.family_params.get("expected_coverage", 0.95))
    coverage_tol = float(case.tolerance.get("coverage_abs", 0.05))

    prices: list[float] = []
    std_errors: list[float] = []
    for seed in seeds:
        variant = case.model_copy(update={"inputs": {**case.inputs, "seed": seed}})
        outcome = client.price(variant, timeout_s=timeout_s)
        prices.append(outcome.price)
        std_errors.append(outcome.std_error or 0.0)

    coverage = coverage_fraction(prices, std_errors, reference, z)
    diff = abs(coverage - expected_coverage)
    passed = diff <= coverage_tol
    return CaseResult(
        case_id=case.id,
        family="statistics",
        verdict="pass" if passed else "fail",
        message=(
            f"coverage={coverage:.3f}" + ("" if passed else f" (expected ~{expected_coverage})")
        ),
        observed={"coverage": coverage, "repeats": float(len(seeds))},
        diff_abs=diff,
    )
