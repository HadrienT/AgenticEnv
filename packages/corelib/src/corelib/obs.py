from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text

from corelib.db import session_scope
from corelib.hashing import args_sha as _args_sha
from corelib.logging import get_logger
from corelib.serialization import to_json

logger = get_logger(__name__)

_MAX_ARGS_BYTES = 4096
_REDACTED = "***REDACTED***"


class ToolInvocation(BaseModel):
    id: str
    ts: datetime
    server: str
    tool: str
    args: dict[str, Any]
    status: str
    duration_ms: int
    error_code: str | None = None
    error_message: str | None = None
    caller: str | None = None
    correlation_id: str | None = None


def _redact(value: Any) -> Any:
    """Recursively replaces `SecretStr`-like values (duck-typed) with a placeholder."""
    if hasattr(value, "get_secret_value"):
        return _REDACTED
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    return value


def _sanitize_args(args: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = _redact(args)
    encoded = to_json(safe)
    if len(encoded.encode("utf-8")) <= _MAX_ARGS_BYTES:
        return safe
    return {"_truncated": True, "_original_bytes": len(encoded.encode("utf-8"))}


def record_tool_invocation(inv: ToolInvocation) -> None:
    """Persists a tool call for observability. Never raises (07-ERRORS-AND-LOGGING.md E5)."""
    try:
        safe_args = _sanitize_args(inv.args)
        with session_scope() as session:
            session.execute(
                text(
                    "INSERT INTO obs.tool_invocations "
                    "(id, ts, server, tool, args, args_sha, status, duration_ms, "
                    " error_code, error_message, caller, correlation_id) "
                    "VALUES (:id, :ts, :server, :tool, CAST(:args AS jsonb), :args_sha, "
                    " :status, :duration_ms, :error_code, :error_message, :caller, :correlation_id)"
                ),
                {
                    "id": inv.id,
                    "ts": inv.ts,
                    "server": inv.server,
                    "tool": inv.tool,
                    "args": to_json(safe_args),
                    "args_sha": _args_sha(inv.args),
                    "status": inv.status,
                    "duration_ms": inv.duration_ms,
                    "error_code": inv.error_code,
                    "error_message": inv.error_message,
                    "caller": inv.caller,
                    "correlation_id": inv.correlation_id,
                },
            )
    except Exception as exc:
        logger.warning(
            "failed to persist tool invocation",
            extra={"tool": inv.tool, "server": inv.server, "error": str(exc)},
        )


@contextmanager
def timed(section: str) -> Iterator[None]:
    """Logs `duration_ms` for the wrapped block. Frontier boundaries only, never in hot loops."""
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info("section completed", extra={"section": section, "duration_ms": duration_ms})
