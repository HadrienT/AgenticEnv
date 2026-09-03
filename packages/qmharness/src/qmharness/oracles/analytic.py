"""Closed-form pricing formulas used only as an *independent cross-reference* when a
golden value is first frozen (WP09 §3.1, §12). Never the system under test, never
imported by `qmharness.checks.*` at runtime — each formula cites its source in a
one-line comment (blueprint/10-TARGET-REPO.md rule R5)."""

from __future__ import annotations

import math


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_price(
    *,
    option_type: str,
    spot: float,
    strike: float,
    rate: float,
    dividend: float,
    vol: float,
    maturity_years: float,
) -> float:
    """Closed-form Black-Scholes-Merton price. Source: Hull, *Options, Futures, and
    Other Derivatives*, 11th ed., eq. 15.20-15.21 (with a continuous dividend yield)."""
    if maturity_years <= 0.0 or vol <= 0.0:
        intrinsic = spot * math.exp(-dividend * maturity_years) - strike * math.exp(
            -rate * maturity_years
        )
        return max(intrinsic, 0.0) if option_type == "call" else max(-intrinsic, 0.0)
    d1 = (math.log(spot / strike) + (rate - dividend + 0.5 * vol * vol) * maturity_years) / (
        vol * math.sqrt(maturity_years)
    )
    d2 = d1 - vol * math.sqrt(maturity_years)
    disc_spot = spot * math.exp(-dividend * maturity_years)
    disc_strike = strike * math.exp(-rate * maturity_years)
    if option_type == "call":
        return disc_spot * _norm_cdf(d1) - disc_strike * _norm_cdf(d2)
    return disc_strike * _norm_cdf(-d2) - disc_spot * _norm_cdf(-d1)
