from __future__ import annotations

import math

import pytest
from qmharness.checks.convergence import check_mc_convergence, fit_loglog_slope
from qmharness.errors import CaseValidationError
from qmharness.schemas import CaseSpec, EngineOutcome


def test_fit_loglog_slope_recovers_known_slope() -> None:
    sizes = [100.0, 400.0, 1600.0, 6400.0]
    # error = C / sqrt(N) => slope should be -0.5
    errors = [1.0 / math.sqrt(n) for n in sizes]
    slope = fit_loglog_slope(sizes, errors)
    assert slope == pytest.approx(-0.5, abs=1e-9)


def test_fit_loglog_slope_requires_at_least_two_points() -> None:
    with pytest.raises(CaseValidationError):
        fit_loglog_slope([100.0], [0.1])


def test_fit_loglog_slope_requires_distinct_sizes() -> None:
    with pytest.raises(CaseValidationError):
        fit_loglog_slope([100.0, 100.0], [0.1, 0.2])


def test_check_mc_convergence_passes_for_expected_slope(base_case: CaseSpec, fake_client) -> None:
    case = base_case.model_copy(
        update={
            "family": "convergence",
            "expected": {"price": 9.4134},
            "family_params": {"sizes": [1000, 4000, 16000, 64000], "size_field": "n_paths"},
            "tolerance": {"slope_abs": 0.1},
        }
    )

    def price_fn(c: CaseSpec) -> EngineOutcome:
        n = c.inputs["n_paths"]
        return EngineOutcome(price=9.4134 + 1.0 / math.sqrt(n))

    fake_client.price_fn = price_fn
    result = check_mc_convergence(case, fake_client, timeout_s=5.0)
    assert result.verdict == "pass"


def test_check_mc_convergence_fails_for_flat_error(base_case: CaseSpec, fake_client) -> None:
    case = base_case.model_copy(
        update={
            "family": "convergence",
            "expected": {"price": 9.4134},
            "family_params": {"sizes": [1000, 4000, 16000, 64000]},
            "tolerance": {"slope_abs": 0.1},
        }
    )
    fake_client.price_fn = lambda c: EngineOutcome(price=9.50)
    result = check_mc_convergence(case, fake_client, timeout_s=5.0)
    assert result.verdict == "fail"


def test_check_mc_convergence_requires_expected_price(base_case: CaseSpec, fake_client) -> None:
    case = base_case.model_copy(
        update={"family": "convergence", "expected": None, "family_params": {"sizes": [1, 2]}}
    )
    with pytest.raises(CaseValidationError):
        check_mc_convergence(case, fake_client, timeout_s=5.0)
