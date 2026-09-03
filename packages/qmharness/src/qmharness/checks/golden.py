"""WP09 §3.1: a golden case is a frozen, externally-verified price. Any nonzero drift
beyond `tolerance.abs` is a regression, never absorbed silently."""

from __future__ import annotations

from qmharness.driver import QuantModelingClient
from qmharness.errors import CaseValidationError
from qmharness.schemas import CaseResult, CaseSpec


def check_golden(case: CaseSpec, client: QuantModelingClient, *, timeout_s: float) -> CaseResult:
    if case.expected is None or "price" not in case.expected:
        raise CaseValidationError(
            f"golden case {case.id!r} has no expected.price", details={"case_id": case.id}
        )
    outcome = client.price(case, timeout_s=timeout_s)
    expected_price = case.expected["price"]
    tol_abs = case.tolerance.get("abs", 1.0e-8)
    diff_abs = abs(outcome.price - expected_price)
    diff_rel = diff_abs / abs(expected_price) if expected_price != 0 else diff_abs
    passed = diff_abs <= tol_abs
    return CaseResult(
        case_id=case.id,
        family="golden",
        verdict="pass" if passed else "fail",
        message=(
            "within tolerance"
            if passed
            else f"price moved by {diff_abs:.3e} (tolerance {tol_abs:.3e})"
        ),
        observed={"price": outcome.price},
        expected=case.expected,
        diff_abs=diff_abs,
        diff_rel=diff_rel,
    )
