from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any

from corelib.errors import AppError
from corelib.ids import new_id
from corelib.obs import ToolInvocation, record_tool_invocation
from corelib.time import utc_now
from mcp.server.mcpserver.exceptions import ToolError

from cppdev_mcp.policy import check_allowlisted, resolve_timeout_s, truncate_data
from cppdev_mcp.schemas import McpServerConfig

_config: McpServerConfig | None = None


def init(config: McpServerConfig) -> None:
    """Binds the process-wide server config. One `cppdev-mcp` server per process (06-CONFIG.md)."""
    global _config
    _config = config


def _current_config() -> McpServerConfig:
    if _config is None:
        raise RuntimeError("cppdev_mcp.tools.dispatch.init() must be called before dispatch()")
    return _config


def dispatch(tool: str, run: Callable[[int], dict[str, Any]]) -> dict[str, Any]:
    """Shared cross-cutting logic for every `cpp.*` tool (M1, M4, M5, M6 of 03-INTERFACES.md §6.2).

    `run` receives the resolved per-tool timeout and returns the raw report as a dict.
    AppErrors become a `ToolError` the model can read and react to; anything else is left
    to propagate so the SDK logs the traceback and reports a generic failure (M3).
    """
    config = _current_config()
    check_allowlisted(config, tool)
    timeout_s = resolve_timeout_s(config, tool)
    started = perf_counter()
    try:
        data = run(timeout_s)
    except AppError as exc:
        _record(
            config, tool, started, status="error", error_code=exc.code, error_message=exc.message
        )
        raise ToolError(exc.message) from exc
    except Exception:
        _record(
            config, tool, started, status="error", error_code="INTERNAL_ERROR", error_message=None
        )
        raise
    payload, truncated = truncate_data(data, config.max_result_bytes)
    _record(config, tool, started, status="ok", error_code=None, error_message=None)
    return {"ok": True, "data": payload, "meta": {"truncated": truncated}}


def _record(
    config: McpServerConfig,
    tool: str,
    started: float,
    *,
    status: str,
    error_code: str | None,
    error_message: str | None,
) -> None:
    duration_ms = int((perf_counter() - started) * 1000)
    record_tool_invocation(
        ToolInvocation(
            id=new_id(),
            ts=utc_now(),
            server=config.name,
            tool=tool,
            args={},
            status=status,
            duration_ms=duration_ms,
            error_code=error_code,
            error_message=error_message,
            caller=None,
        )
    )
