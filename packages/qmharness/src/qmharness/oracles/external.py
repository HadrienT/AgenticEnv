"""An optional, out-of-repo pricing source used to verify a golden value *before it is
frozen* (WP09 §3.1, §6). Test-only dependency, never a runtime one for `qm.run`."""

from __future__ import annotations

from typing import Protocol

from qmharness.errors import ExternalOracleUnavailableError


class ExternalOracle(Protocol):
    name: str

    def black_scholes_price(
        self,
        *,
        option_type: str,
        spot: float,
        strike: float,
        rate: float,
        dividend: float,
        vol: float,
        maturity_years: float,
    ) -> float: ...


class QuantLibOracle:
    """Only usable if `QuantLib` is installed — an independent, third-party library,
    never added to `qmharness`'s runtime dependencies (WP09 §6)."""

    name = "QuantLib"

    def __init__(self) -> None:
        try:
            import QuantLib as ql  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ExternalOracleUnavailableError(
                "QuantLib is not installed; the external oracle is optional", details={}
            ) from exc
        self._ql = ql

    def black_scholes_price(
        self,
        *,
        option_type: str,
        spot: float,
        strike: float,
        rate: float,
        dividend: float,
        vol: float,
        maturity_years: float,
    ) -> float:
        ql = self._ql
        calendar = ql.NullCalendar()
        today = ql.Date.todaysDate()
        ql.Settings.instance().evaluationDate = today
        maturity = today + ql.Period(int(round(maturity_years * 365)), ql.Days)
        payoff = ql.PlainVanillaPayoff(
            ql.Option.Call if option_type == "call" else ql.Option.Put, strike
        )
        exercise = ql.EuropeanExercise(maturity)
        option = ql.VanillaOption(payoff, exercise)
        spot_handle = ql.QuoteHandle(ql.SimpleQuote(spot))
        rate_curve = ql.YieldTermStructureHandle(ql.FlatForward(today, rate, ql.Actual365Fixed()))
        div_curve = ql.YieldTermStructureHandle(
            ql.FlatForward(today, dividend, ql.Actual365Fixed())
        )
        vol_curve = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(today, calendar, vol, ql.Actual365Fixed())
        )
        process = ql.BlackScholesMertonProcess(spot_handle, div_curve, rate_curve, vol_curve)
        option.setPricingEngine(ql.AnalyticEuropeanEngine(process))
        return float(option.NPV())
