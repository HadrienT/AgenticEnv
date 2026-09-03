from __future__ import annotations

import pytest
from qmharness.checks.cross_engine import check_cross_engine
from qmharness.errors import CaseValidationError
from qmharness.schemas import CaseSpec, EngineOutcome


def test_check_cross_engine_requires_compare_engine(base_case: CaseSpec, fake_client) -> None:
    with pytest.raises(CaseValidationError):
        check_cross_engine(base_case, fake_client, timeout_s=5.0)


def test_check_cross_engine_passes_within_relative_tolerance(
    base_case: CaseSpec, fake_client
) -> None:
    case = base_case.model_copy(
        update={
            "family": "cross_engine",
            "family_params": {"compare_engine": "monte_carlo"},
            "tolerance": {"rel": 1e-2},
        }
    )
    prices = {"analytic": 9.4134, "monte_carlo": 9.42}
    fake_client.price_fn = lambda c: EngineOutcome(price=prices[c.engine])
    result = check_cross_engine(case, fake_client, timeout_s=5.0)
    assert result.verdict == "pass"


def test_check_cross_engine_uses_sigma_multiple_for_mc(base_case: CaseSpec, fake_client) -> None:
    case = base_case.model_copy(
        update={
            "family": "cross_engine",
            "family_params": {"compare_engine": "monte_carlo", "sigma_multiple": 3.0},
        }
    )

    def price_fn(c: CaseSpec) -> EngineOutcome:
        if c.engine == "monte_carlo":
            return EngineOutcome(price=9.50, std_error=0.01)
        return EngineOutcome(price=9.4134, std_error=None)

    fake_client.price_fn = price_fn
    result = check_cross_engine(case, fake_client, timeout_s=5.0)
    assert result.verdict == "fail"
