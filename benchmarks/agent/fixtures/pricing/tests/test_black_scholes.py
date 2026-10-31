from pricing.black_scholes import call_price


def test_atm_call_one_year():
    assert abs(call_price(100, 100, 0.0, 0.2, 1.0) - 7.9656) < 1e-3


def test_atm_call_three_months():
    assert abs(call_price(100, 100, 0.0, 0.2, 0.25) - 3.9878) < 1e-3
