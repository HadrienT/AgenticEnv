import math
import random


def price_call(spot, strike, rate, vol, maturity, n_paths, seed=1):
    rng = random.Random(seed)
    total = 0.0
    for _ in range(n_paths):
        z = rng.gauss(0.0, 1.0)
        terminal = spot * math.exp((rate - 0.5 * vol * vol) * maturity + vol * math.sqrt(maturity) * z)
        total += max(terminal - strike, 0.0)
    return total / n_paths
