"""WP09 §3.3: financial invariants. Each pure helper below takes plain floats (no I/O,
directly unit-testable); `check_invariant` fetches exactly the prices each invariant
needs via `client.price()` then delegates the math to the matching helper.

`case.family_params["invariant"]` selects the branch:
- `put_call_parity`: needs `case.inputs.{spot,strike,rate,maturity_years}` (+ optional
  `dividend`); prices both legs by overriding `option_type`.
- `no_arbitrage_bounds`: same inputs, prices the call as given by `case`.
- `monotonicity_strike`: needs `family_params.{low_strike,high_strike}`.
- `barrier_parity`: needs `family_params.vanilla_instrument` (in + out == vanilla).
- `digital_call_spread_limit`: needs `family_params.call_spread_instrument`.
"""

from __future__ import annotations

import math

from qmharness.driver import QuantModelingClient
from qmharness.errors import CaseValidationError
from qmharness.schemas import CaseResult, CaseSpec


def put_call_parity_gap(
    call_price: float,
    put_price: float,
    spot: float,
    strike: float,
    rate: float,
    dividend: float,
    maturity_years: float,
) -> float:
    """`C - P = S e^{-qT} - K e^{-rT}` (blueprint/08-TESTING.md §3.1)."""
    lhs = call_price - put_price
    rhs = spot * math.exp(-dividend * maturity_years) - strike * math.exp(-rate * maturity_years)
    return lhs - rhs


def no_arbitrage_gap(
    call_price: float,
    spot: float,
    strike: float,
    rate: float,
    dividend: float,
    maturity_years: float,
) -> float:
    """Positive gap => the no-arbitrage bound is violated."""
    lower = max(
        spot * math.exp(-dividend * maturity_years) - strike * math.exp(-rate * maturity_years),
        0.0,
    )
    upper = spot * math.exp(-dividend * maturity_years)
    if call_price < lower:
        return lower - call_price
    if call_price > upper:
        return call_price - upper
    return 0.0


def monotonicity_violation(
    low_strike_price: float, high_strike_price: float, *, increasing: bool
) -> float:
    """Call must be non-increasing in strike, put non-decreasing. Returns the violation
    amount (0.0 if the ordering holds)."""
    diff = high_strike_price - low_strike_price
    return max(-diff, 0.0) if increasing else max(diff, 0.0)


def barrier_parity_gap(in_price: float, out_price: float, vanilla_price: float) -> float:
    """`in + out == vanilla` for complementary barriers, same strike/maturity."""
    return (in_price + out_price) - vanilla_price


def digital_call_spread_limit_gap(digital_price: float, call_spread_price: float) -> float:
    """A sufficiently tight call spread converges to the digital payoff."""
    return digital_price - call_spread_price


def check_invariant(case: CaseSpec, client: QuantModelingClient, *, timeout_s: float) -> CaseResult:
    invariant = case.family_params.get("invariant")
    tol_abs = case.tolerance.get("abs", 1.0e-6)
    observed: dict[str, float]

    if invariant == "put_call_parity":
        call = client.price(
            case.model_copy(update={"inputs": {**case.inputs, "option_type": "call"}}),
            timeout_s=timeout_s,
        )
        put = client.price(
            case.model_copy(update={"inputs": {**case.inputs, "option_type": "put"}}),
            timeout_s=timeout_s,
        )
        gap = put_call_parity_gap(
            call.price,
            put.price,
            case.inputs["spot"],
            case.inputs["strike"],
            case.inputs["rate"],
            case.inputs.get("dividend", 0.0),
            case.inputs["maturity_years"],
        )
        observed = {"call_price": call.price, "put_price": put.price, "gap": gap}
    elif invariant == "no_arbitrage_bounds":
        outcome = client.price(case, timeout_s=timeout_s)
        gap = no_arbitrage_gap(
            outcome.price,
            case.inputs["spot"],
            case.inputs["strike"],
            case.inputs["rate"],
            case.inputs.get("dividend", 0.0),
            case.inputs["maturity_years"],
        )
        observed = {"price": outcome.price, "gap": gap}
    elif invariant == "monotonicity_strike":
        low_strike = float(case.family_params["low_strike"])
        high_strike = float(case.family_params["high_strike"])
        option_type = case.inputs.get("option_type", "call")
        low = client.price(
            case.model_copy(update={"inputs": {**case.inputs, "strike": low_strike}}),
            timeout_s=timeout_s,
        )
        high = client.price(
            case.model_copy(update={"inputs": {**case.inputs, "strike": high_strike}}),
            timeout_s=timeout_s,
        )
        gap = monotonicity_violation(low.price, high.price, increasing=(option_type == "put"))
        observed = {"low_strike_price": low.price, "high_strike_price": high.price, "gap": gap}
    elif invariant == "barrier_parity":
        in_price = client.price(case, timeout_s=timeout_s)
        out_price = client.price(
            case.model_copy(update={"inputs": {**case.inputs, "barrier_direction": "out"}}),
            timeout_s=timeout_s,
        )
        vanilla_price = client.price(
            case.model_copy(update={"instrument": case.family_params["vanilla_instrument"]}),
            timeout_s=timeout_s,
        )
        gap = barrier_parity_gap(in_price.price, out_price.price, vanilla_price.price)
        observed = {
            "in_price": in_price.price,
            "out_price": out_price.price,
            "vanilla_price": vanilla_price.price,
            "gap": gap,
        }
    elif invariant == "digital_call_spread_limit":
        digital = client.price(case, timeout_s=timeout_s)
        spread = client.price(
            case.model_copy(update={"instrument": case.family_params["call_spread_instrument"]}),
            timeout_s=timeout_s,
        )
        gap = digital_call_spread_limit_gap(digital.price, spread.price)
        observed = {"digital_price": digital.price, "call_spread_price": spread.price, "gap": gap}
    else:
        raise CaseValidationError(
            f"unknown invariant {invariant!r} for case {case.id!r}", details={"case_id": case.id}
        )

    passed = abs(observed["gap"]) <= tol_abs
    return CaseResult(
        case_id=case.id,
        family="invariants",
        verdict="pass" if passed else "fail",
        message=(
            "within tolerance"
            if passed
            else f"invariant {invariant} violated by {observed['gap']:.3e}"
        ),
        observed=observed,
        diff_abs=abs(observed["gap"]),
    )
