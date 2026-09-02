from __future__ import annotations

from typing import NewType

from corelib.errors import ValidationError

# Decimal representation: 0.03 means 3%, never "3". Guards against the #1
# silent-bug cause in this domain (09-CONVENTIONS.md §3).
Rate = NewType("Rate", float)
Vol = NewType("Vol", float)
Year = NewType("Year", float)

# Defaults mirror configs/quantlab.yaml -> sanity. Callers with domain knowledge
# of that file should pass explicit bounds; corelib itself reads no YAML (WP01 §4.3).
_DEFAULT_RATE_ABS_MAX = 1.0
_DEFAULT_VOL_MAX = 5.0
_DEFAULT_MATURITY_YEARS_MAX = 100.0


def as_rate(x: float, *, max_abs: float = _DEFAULT_RATE_ABS_MAX) -> Rate:
    """Validates a decimal rate (0.03 == 3%); rejects likely percent-point input."""
    if abs(x) > max_abs:
        raise ValidationError(
            f"rate={x} out of sanity bounds; expected a decimal (3% => 0.03)",
            details={"field": "rate", "value": x, "max": max_abs},
        )
    return Rate(x)


def as_vol(x: float, *, max_value: float = _DEFAULT_VOL_MAX) -> Vol:
    """Validates a decimal volatility (0.20 == 20 vol points)."""
    if x < 0 or x > max_value:
        raise ValidationError(
            f"vol={x} out of sanity bounds; expected a decimal in [0, {max_value}]",
            details={"field": "vol", "value": x, "max": max_value},
        )
    return Vol(x)


def as_year(x: float, *, max_years: float = _DEFAULT_MATURITY_YEARS_MAX) -> Year:
    """Validates a fractional-year maturity; must be strictly positive."""
    if x <= 0 or x > max_years:
        raise ValidationError(
            f"maturity_years={x} out of sanity bounds; expected in (0, {max_years}]",
            details={"field": "maturity_years", "value": x, "max": max_years},
        )
    return Year(x)
