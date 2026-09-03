from __future__ import annotations

import pytest
from qmharness.checks.greeks import check_greeks_cross_method, max_pairwise_rel_diff
from qmharness.errors import CaseValidationError
from qmharness.schemas import CaseSpec, GreeksOutcome


def test_max_pairwise_rel_diff_zero_when_identical() -> None:
    values = {"pathwise": {"delta": 0.6}, "finite_difference": {"delta": 0.6}}
    assert max_pairwise_rel_diff(values) == {"delta": 0.0}


def test_max_pairwise_rel_diff_detects_worst_pair() -> None:
    values = {
        "pathwise": {"delta": 0.60},
        "finite_difference": {"delta": 0.605},
        "analytic": {"delta": 0.50},
    }
    result = max_pairwise_rel_diff(values)
    assert result["delta"] == pytest.approx(abs(0.605 - 0.50) / 0.605)


def test_max_pairwise_rel_diff_requires_two_methods() -> None:
    with pytest.raises(CaseValidationError):
        max_pairwise_rel_diff({"pathwise": {"delta": 0.6}})


def test_check_greeks_cross_method_passes_within_tolerance(
    base_case: CaseSpec, fake_client
) -> None:
    case = base_case.model_copy(
        update={
            "family": "greeks",
            "family_params": {"methods": ["pathwise", "finite_difference"], "which": ["delta"]},
            "tolerance": {"rel": 1e-2},
        }
    )
    fake_client.greeks_fn = lambda c, which: GreeksOutcome(values={"delta": 0.60})
    result = check_greeks_cross_method(case, fake_client, timeout_s=5.0)
    assert result.verdict == "pass"


def test_check_greeks_cross_method_fails_beyond_tolerance(base_case: CaseSpec, fake_client) -> None:
    case = base_case.model_copy(
        update={
            "family": "greeks",
            "family_params": {"methods": ["pathwise", "finite_difference"], "which": ["delta"]},
            "tolerance": {"rel": 1e-3},
        }
    )

    def greeks_fn(c: CaseSpec, which: list[str]) -> GreeksOutcome:
        value = 0.60 if c.method == "pathwise" else 0.70
        return GreeksOutcome(values={"delta": value})

    fake_client.greeks_fn = greeks_fn
    result = check_greeks_cross_method(case, fake_client, timeout_s=5.0)
    assert result.verdict == "fail"


def test_check_greeks_cross_method_requires_methods(base_case: CaseSpec, fake_client) -> None:
    case = base_case.model_copy(update={"family": "greeks", "family_params": {}})
    with pytest.raises(CaseValidationError):
        check_greeks_cross_method(case, fake_client, timeout_s=5.0)
