from __future__ import annotations

from datetime import UTC, datetime

import pytest
from corelib.time import FixedClock, make_clock, utc_now


def test_utc_now_is_aware_and_utc() -> None:
    now = utc_now()
    assert now.tzinfo is not None
    assert now.utcoffset() == UTC.utcoffset(now)


def test_fixed_clock_returns_injected_instant() -> None:
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    clock = FixedClock(instant)
    assert clock() == instant


def test_fixed_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 1, 1))


def test_make_clock_defaults_to_utc_now() -> None:
    assert make_clock() is utc_now
