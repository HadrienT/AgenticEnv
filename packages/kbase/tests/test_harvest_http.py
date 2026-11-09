from __future__ import annotations

import pytest
from corelib.errors import DependencyError
from kbase.harvest.http import PoliteClient, RawResponse


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class _Scripted:
    def __init__(self, clock: _Clock, responses: list[RawResponse], latency_s: float = 0.0) -> None:
        self.clock = clock
        self.responses = responses
        self.latency_s = latency_s
        self.calls = 0

    def fetch(self, url: str, *, headers: dict[str, str], timeout_s: float) -> RawResponse:
        assert headers["User-Agent"] == "ua"
        self.calls += 1
        self.clock.now += self.latency_s
        return self.responses.pop(0)


def _ok(status: int = 200, retry_after: str | None = None) -> RawResponse:
    return RawResponse(status=status, url="u", body=b"x", retry_after=retry_after)


def _client(clock: _Clock, transport: _Scripted, attempts: int = 3) -> PoliteClient:
    return PoliteClient(
        user_agent="ua", min_interval_s=3.0, max_attempts=attempts, timeout_s=1,
        transport=transport, clock=clock.time, sleep=clock.sleep,
    )  # fmt: skip


def test_interval_is_counted_from_the_end_of_the_previous_request() -> None:
    clock = _Clock()
    transport = _Scripted(clock, [_ok(), _ok()], latency_s=5.0)
    client = _client(clock, transport)
    client.get("a")
    client.get("b")
    assert clock.sleeps == [3.0]  # a 5 s response still leaves 3 s before the next


def test_retries_a_503_then_returns_the_200() -> None:
    clock = _Clock()
    transport = _Scripted(clock, [_ok(503), _ok(200)])
    assert _client(clock, transport).get("a").status == 200
    assert transport.calls == 2


def test_retry_after_is_honoured() -> None:
    clock = _Clock()
    transport = _Scripted(clock, [_ok(429, retry_after="7"), _ok(200)])
    _client(clock, transport).get("a")
    assert 7.0 in clock.sleeps


def test_404_is_returned_without_retry() -> None:
    clock = _Clock()
    transport = _Scripted(clock, [_ok(404)])
    assert _client(clock, transport).get("a").status == 404
    assert transport.calls == 1


def test_gives_up_after_max_attempts() -> None:
    clock = _Clock()
    transport = _Scripted(clock, [_ok(503), _ok(503)])
    with pytest.raises(DependencyError):
        _client(clock, transport, attempts=2).get("a")
