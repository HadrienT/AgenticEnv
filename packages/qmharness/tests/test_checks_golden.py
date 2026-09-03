from __future__ import annotations

import pytest
from qmharness.checks.golden import check_golden
from qmharness.errors import CaseValidationError
from qmharness.schemas import CaseSpec, EngineOutcome


def test_check_golden_passes_within_tolerance(base_case: CaseSpec, fake_client) -> None:
    case = base_case.model_copy(update={"expected": {"price": 9.4134}, "tolerance": {"abs": 1e-3}})
    fake_client.price_fn = lambda c: EngineOutcome(price=9.4135)
    result = check_golden(case, fake_client, timeout_s=5.0)
    assert result.verdict == "pass"
    assert result.diff_abs is not None and result.diff_abs < 1e-3


def test_check_golden_fails_beyond_tolerance(base_case: CaseSpec, fake_client) -> None:
    case = base_case.model_copy(update={"expected": {"price": 9.4134}, "tolerance": {"abs": 1e-6}})
    fake_client.price_fn = lambda c: EngineOutcome(price=9.50)
    result = check_golden(case, fake_client, timeout_s=5.0)
    assert result.verdict == "fail"


def test_check_golden_requires_expected_price(base_case: CaseSpec, fake_client) -> None:
    case = base_case.model_copy(update={"expected": None})
    with pytest.raises(CaseValidationError):
        check_golden(case, fake_client, timeout_s=5.0)
