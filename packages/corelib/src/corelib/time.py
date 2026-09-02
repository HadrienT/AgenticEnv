from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def __call__(self) -> datetime: ...


def utc_now() -> datetime:
    """Aware, UTC `datetime`. Never use `datetime.now()` naively (09-CONVENTIONS.md N5)."""
    return datetime.now(UTC)


class FixedClock:
    """Injectable clock for tests: `FixedClock(instant)` replaces `utc_now`."""

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FixedClock requires an aware (UTC) datetime")
        self._instant = instant

    def __call__(self) -> datetime:
        return self._instant


def make_clock(fixed: datetime | None = None) -> Callable[[], datetime]:
    """Returns `utc_now` by default, or a `FixedClock` when `fixed` is given (tests)."""
    if fixed is None:
        return utc_now
    return FixedClock(fixed)
