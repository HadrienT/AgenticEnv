from __future__ import annotations

import pytest
from corelib.errors import ValidationError
from corelib.units import as_rate, as_vol, as_year


def test_as_rate_accepts_decimal_value() -> None:
    assert as_rate(0.03) == 0.03


def test_as_rate_rejects_percent_point_input() -> None:
    with pytest.raises(ValidationError):
        as_rate(3.0)


def test_as_vol_rejects_negative_value() -> None:
    with pytest.raises(ValidationError):
        as_vol(-0.1)


def test_as_vol_accepts_zero() -> None:
    assert as_vol(0.0) == 0.0


def test_as_year_rejects_non_positive_value() -> None:
    with pytest.raises(ValidationError):
        as_year(0.0)


def test_as_year_accepts_positive_value() -> None:
    assert as_year(1.5) == 1.5
