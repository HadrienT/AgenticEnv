from __future__ import annotations

import pytest
from qmharness.checks.invariants import (
    barrier_parity_gap,
    check_invariant,
    digital_call_spread_limit_gap,
    monotonicity_violation,
    no_arbitrage_gap,
    put_call_parity_gap,
)
from qmharness.errors import CaseValidationError
from qmharness.schemas import CaseSpec, EngineOutcome


def test_put_call_parity_gap_is_zero_when_parity_holds() -> None:
    import math

    spot, strike, rate, dividend, maturity = 100.0, 95.0, 0.03, 0.01, 0.5
    rhs = spot * math.exp(-dividend * maturity) - strike * math.exp(-rate * maturity)
    call_price = 10.0
    put_price = call_price - rhs
    gap = put_call_parity_gap(call_price, put_price, spot, strike, rate, dividend, maturity)
    assert abs(gap) < 1e-9


def test_put_call_parity_gap_detects_violation() -> None:
    gap = put_call_parity_gap(10.0, 3.0, 100.0, 95.0, 0.03, 0.0, 1.0)
    assert abs(gap) > 1e-6


def test_no_arbitrage_gap_zero_within_bounds() -> None:
    assert no_arbitrage_gap(5.0, 100.0, 100.0, 0.03, 0.0, 1.0) == 0.0


def test_no_arbitrage_gap_detects_below_lower_bound() -> None:
    gap = no_arbitrage_gap(-1.0, 100.0, 100.0, 0.03, 0.0, 1.0)
    assert gap > 0.0


def test_no_arbitrage_gap_detects_above_upper_bound() -> None:
    gap = no_arbitrage_gap(150.0, 100.0, 100.0, 0.03, 0.0, 1.0)
    assert gap > 0.0


def test_monotonicity_violation_call_decreasing() -> None:
    assert monotonicity_violation(10.0, 8.0, increasing=False) == 0.0
    assert monotonicity_violation(8.0, 10.0, increasing=False) == pytest.approx(2.0)


def test_monotonicity_violation_put_increasing() -> None:
    assert monotonicity_violation(5.0, 8.0, increasing=True) == 0.0
    assert monotonicity_violation(8.0, 5.0, increasing=True) == pytest.approx(3.0)


def test_barrier_parity_gap() -> None:
    assert barrier_parity_gap(4.0, 6.0, 10.0) == pytest.approx(0.0)
    assert barrier_parity_gap(4.0, 6.5, 10.0) == pytest.approx(0.5)


def test_digital_call_spread_limit_gap() -> None:
    assert digital_call_spread_limit_gap(1.0, 0.98) == pytest.approx(0.02)


def test_check_invariant_put_call_parity_dispatch(base_case: CaseSpec, fake_client) -> None:
    import math

    case = base_case.model_copy(
        update={"family": "invariants", "family_params": {"invariant": "put_call_parity"}}
    )
    spot, strike, rate, dividend, maturity = 100.0, 100.0, 0.03, 0.0, 1.0
    rhs = spot * math.exp(-dividend * maturity) - strike * math.exp(-rate * maturity)

    def price_fn(c: CaseSpec) -> EngineOutcome:
        if c.inputs["option_type"] == "call":
            return EngineOutcome(price=9.4134)
        return EngineOutcome(price=9.4134 - rhs)

    fake_client.price_fn = price_fn
    result = check_invariant(case, fake_client, timeout_s=5.0)
    assert result.verdict == "pass"


def test_check_invariant_unknown_kind_raises(base_case: CaseSpec, fake_client) -> None:
    case = base_case.model_copy(
        update={"family": "invariants", "family_params": {"invariant": "not_a_real_invariant"}}
    )
    with pytest.raises(CaseValidationError):
        check_invariant(case, fake_client, timeout_s=5.0)
