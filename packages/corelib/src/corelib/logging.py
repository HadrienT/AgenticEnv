from __future__ import annotations

import contextvars
import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from corelib.time import utc_now

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)

# Attributes every stdlib LogRecord carries; anything else came from `extra=`.
_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": utc_now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        cid = _correlation_id.get()
        if cid is not None:
            payload["correlation_id"] = cid
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return
    # stderr, never stdout: stdio-transport MCP servers (agentmem-mcp,
    # codeintel-mcp, cppdev-mcp, kbase-mcp) reserve stdout exclusively for
    # JSON-RPC frames — any log line written to stdout corrupts the MCP
    # transport (confirmed failure mode during WP08's OpenHands smoke test).
    # journald/systemd capture stderr identically to stdout, so this is a
    # no-op for the non-MCP (systemd-managed) call sites.
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(_JSONFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Structured JSON logger: every record carries ts/level/logger/msg + correlation_id."""
    _configure_root()
    return logging.getLogger(name)


@contextmanager
def bind_correlation_id(cid: str) -> Iterator[None]:
    """Every log emitted within this block carries `correlation_id=cid`."""
    token = _correlation_id.set(cid)
    try:
        yield
    finally:
        _correlation_id.reset(token)
