from __future__ import annotations

from qmharness.oracles.analytic import black_scholes_price


def test_black_scholes_call_atm_matches_known_value() -> None:
    # Known reference value for this parameter set (Hull 11th ed. eq. 15.20, S=K=100,
    # r=0.03, q=0.0, vol=0.20, T=1.0) -- cross-checked independently, see benchmarks/golden.
    price = black_scholes_price(
        option_type="call",
        spot=100.0,
        strike=100.0,
        rate=0.03,
        dividend=0.0,
        vol=0.20,
        maturity_years=1.0,
    )
    assert abs(price - 9.4134) < 1.0e-4


def test_black_scholes_put_call_parity_holds_exactly() -> None:
    kwargs = dict(spot=100.0, strike=95.0, rate=0.02, dividend=0.01, vol=0.25, maturity_years=0.5)
    call = black_scholes_price(option_type="call", **kwargs)
    put = black_scholes_price(option_type="put", **kwargs)
    import math

    lhs = call - put
    rhs = kwargs["spot"] * math.exp(-kwargs["dividend"] * kwargs["maturity_years"]) - kwargs[
        "strike"
    ] * math.exp(-kwargs["rate"] * kwargs["maturity_years"])
    assert abs(lhs - rhs) < 1.0e-10


def test_black_scholes_zero_vol_is_discounted_intrinsic() -> None:
    price = black_scholes_price(
        option_type="call",
        spot=110.0,
        strike=100.0,
        rate=0.03,
        dividend=0.0,
        vol=1.0e-9,
        maturity_years=1.0,
    )
    import math

    expected = 110.0 - 100.0 * math.exp(-0.03)
    assert abs(price - expected) < 1.0e-6
