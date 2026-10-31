from pricing.black_scholes import call_price


def test_atm_call_short_maturity():
    assert abs(call_price(100, 100, 0.0, 0.2, 1.0) - 7.9656) < 1e-3
