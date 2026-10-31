import math


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def call_price(spot, strike, rate, vol, maturity):
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * maturity) / (vol * math.sqrt(maturity))
    d2 = d1 - vol * maturity
    return spot * norm_cdf(d1) - strike * math.exp(-rate * maturity) * norm_cdf(d2)


def put_price(spot, strike, rate, vol, maturity):
    call = call_price(spot, strike, rate, vol, maturity)
    return call + strike * math.exp(-rate * maturity) - spot
