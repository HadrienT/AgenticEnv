"""WP09 §3.2: cross-engine / cross-method coherence for the same instrument.

`case.family_params` for this family:
- `compare_engine` (required): the second engine to price with.
- `compare_method` (optional, default `case.method`): the second method.
- `sigma_multiple` (optional, default 3.0): MC comparisons pass within N combined
  standard errors, per WP09 §3.2's table.
"""

from __future__ import annotations

import math

from qmharness.driver import QuantModelingClient
from qmharness.errors import CaseValidationError
from qmharness.schemas import CaseResult, CaseSpec


def check_cross_engine(
    case: CaseSpec, client: QuantModelingClient, *, timeout_s: float
) -> CaseResult:
    compare_engine = case.family_params.get("compare_engine")
    if compare_engine is None:
        raise CaseValidationError(
            f"cross_engine case {case.id!r} needs family_params.compare_engine",
            details={"case_id": case.id},
        )
    compare_method = case.family_params.get("compare_method", case.method)

    baseline = client.price(case, timeout_s=timeout_s)
    variant = case.model_copy(update={"method": compare_method, "engine": compare_engine})
    candidate = client.price(variant, timeout_s=timeout_s)

    diff_abs = abs(baseline.price - candidate.price)
    diff_rel = diff_abs / abs(baseline.price) if baseline.price != 0 else diff_abs

    if baseline.std_error is not None or candidate.std_error is not None:
        sigma_multiple = float(case.family_params.get("sigma_multiple", 3.0))
        combined_se = math.sqrt(
            (baseline.std_error or 0.0) ** 2 + (candidate.std_error or 0.0) ** 2
        )
        bound = sigma_multiple * combined_se
        passed = diff_abs <= bound if combined_se > 0 else diff_abs == 0
        bound_desc = f"{sigma_multiple}x combined std-error ({bound:.3e})"
    else:
        tol_rel = float(case.tolerance.get("rel", 1.0e-3))
        passed = diff_rel <= tol_rel
        bound_desc = f"relative tolerance {tol_rel:.3e}"

    return CaseResult(
        case_id=case.id,
        family="cross_engine",
        verdict="pass" if passed else "fail",
        message=(f"within {bound_desc}" if passed else f"diff {diff_abs:.3e} exceeds {bound_desc}"),
        observed={
            f"{case.engine}_{case.method}": baseline.price,
            f"{compare_engine}_{compare_method}": candidate.price,
        },
        diff_abs=diff_abs,
        diff_rel=diff_rel,
    )
