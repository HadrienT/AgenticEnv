from __future__ import annotations

import pytest
from qmharness.checks.statistics import check_ci_coverage, check_determinism, coverage_fraction
from qmharness.errors import CaseValidationError
from qmharness.schemas import CaseSpec, EngineOutcome


def test_coverage_fraction_all_hits() -> None:
    prices = [10.0, 10.1, 9.9]
    std_errors = [0.2, 0.2, 0.2]
    assert coverage_fraction(prices, std_errors, reference=10.0, z=1.96) == 1.0


def test_coverage_fraction_partial_hits() -> None:
    prices = [10.0, 20.0]
    std_errors = [0.1, 0.1]
    assert coverage_fraction(prices, std_errors, reference=10.0, z=1.96) == 0.5


def test_coverage_fraction_requires_at_least_one_repeat() -> None:
    with pytest.raises(CaseValidationError):
        coverage_fraction([], [], reference=10.0, z=1.96)


def test_check_determinism_passes_for_identical_repeats(base_case: CaseSpec, fake_client) -> None:
    fake_client.price_fn = lambda c: EngineOutcome(price=9.4134)
    result = check_determinism(base_case, fake_client, timeout_s=5.0)
    assert result.verdict == "pass"


def test_check_determinism_fails_for_differing_repeats(base_case: CaseSpec, fake_client) -> None:
    calls = {"n": 0}

    def price_fn(c: CaseSpec) -> EngineOutcome:
        calls["n"] += 1
        return EngineOutcome(price=9.4134 + 0.001 * calls["n"])

    fake_client.price_fn = price_fn
    result = check_determinism(base_case, fake_client, timeout_s=5.0)
    assert result.verdict == "fail"


def test_check_ci_coverage_passes_near_expected(base_case: CaseSpec, fake_client) -> None:
    case = base_case.model_copy(
        update={
            "family": "statistics",
            "expected": {"price": 9.4134},
            "family_params": {"seeds": list(range(20)), "z": 1.96, "expected_coverage": 0.95},
            "tolerance": {"coverage_abs": 0.2},
        }
    )
    fake_client.price_fn = lambda c: EngineOutcome(price=9.4134, std_error=0.05)
    result = check_ci_coverage(case, fake_client, timeout_s=5.0)
    assert result.verdict == "pass"


def test_check_ci_coverage_requires_expected_price(base_case: CaseSpec, fake_client) -> None:
    case = base_case.model_copy(
        update={"family": "statistics", "expected": None, "family_params": {"seeds": [1]}}
    )
    with pytest.raises(CaseValidationError):
        check_ci_coverage(case, fake_client, timeout_s=5.0)
