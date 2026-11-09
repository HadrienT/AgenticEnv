"""Polite HTTP for arXiv: one request per `min_interval_s` across hosts, retries on
429/5xx with backoff, `Retry-After` honoured (arXiv API terms: one request every 3 s)."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Protocol

from corelib.errors import DependencyError
from pydantic import BaseModel

_RETRYABLE = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_AFTER_S = 120.0


class RawResponse(BaseModel):
    status: int
    url: str  # final URL, after redirects
    body: bytes
    retry_after: str | None = None


class Transport(Protocol):
    def fetch(self, url: str, *, headers: dict[str, str], timeout_s: float) -> RawResponse: ...


class UrllibTransport:
    """Follows redirects; an HTTP error status is a response, not an exception."""

    def fetch(self, url: str, *, headers: dict[str, str], timeout_s: float) -> RawResponse:
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
                return RawResponse(status=response.status, url=response.url, body=response.read())
        except urllib.error.HTTPError as exc:
            return RawResponse(
                status=exc.code,
                url=exc.url or url,
                body=exc.read() or b"",
                retry_after=exc.headers.get("Retry-After") if exc.headers else None,
            )


class PoliteClient:
    def __init__(
        self,
        *,
        user_agent: str,
        min_interval_s: float,
        max_attempts: int,
        timeout_s: float,
        transport: Transport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._headers = {"User-Agent": user_agent}
        self._min_interval_s = min_interval_s
        self._max_attempts = max_attempts
        self._timeout_s = timeout_s
        self._transport = transport or UrllibTransport()
        self._clock = clock
        self._sleep = sleep
        self._last_request_at: float | None = None
        self.requests_made = 0

    def _wait_turn(self) -> None:
        """Measured from the end of the previous request, so a slow response still
        leaves the full interval before the next one."""
        if self._last_request_at is not None:
            remaining = self._min_interval_s - (self._clock() - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)

    def get(self, url: str) -> RawResponse:
        """The final response; non-retryable statuses (404…) are returned as they are."""
        last_error = ""
        for attempt in range(self._max_attempts):
            self._wait_turn()
            self.requests_made += 1
            try:
                response = self._transport.fetch(
                    url, headers=self._headers, timeout_s=self._timeout_s
                )
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self._last_request_at = self._clock()
                last_error = str(exc)
            else:
                self._last_request_at = self._clock()
                if response.status not in _RETRYABLE:
                    return response
                last_error = f"HTTP {response.status}"
                if response.retry_after and response.retry_after.isdigit():
                    self._sleep(min(float(response.retry_after), _MAX_RETRY_AFTER_S))
                    continue
            if attempt < self._max_attempts - 1:
                self._sleep(self._min_interval_s * (2**attempt))
        raise DependencyError(
            f"GET {url} failed after {self._max_attempts} attempts: {last_error}",
            details={"url": url, "attempts": self._max_attempts},
        )
