from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any

from corelib.errors import AppError
from corelib.ids import new_id
from corelib.obs import ToolInvocation, record_tool_invocation
from corelib.time import utc_now
from kbase.usage import summarize_result
from mcp.server.mcpserver.exceptions import ToolError

from kbase_mcp.policy import check_allowlisted, resolve_timeout_s, truncate_data
from kbase_mcp.schemas import McpServerConfig

_config: McpServerConfig | None = None


def init(config: McpServerConfig) -> None:
    """Binds the process-wide server config. One `kbase-mcp` server per process."""
    global _config
    _config = config


def _current_config() -> McpServerConfig:
    if _config is None:
        raise RuntimeError("kbase_mcp.tools.dispatch.init() must be called before dispatch()")
    return _config


def caller() -> str | None:
    """Who is calling, for the invocation log: `AGX_MCP_CALLER` when the client's MCP
    config sets it, otherwise the directory the client started the server from. `uv run
    --directory` changes the working directory but leaves `PWD` alone, so `PWD` is the
    client's project (`quant-modeling` for a Claude Code session opened there)."""
    explicit = os.environ.get("AGX_MCP_CALLER")
    if explicit:
        return explicit
    pwd = os.environ.get("PWD")
    return Path(pwd).name if pwd else None


def call_args(values: dict[str, Any]) -> dict[str, Any]:
    """The arguments a tool was called with, without the ones left to their default None."""
    return {k: v for k, v in values.items() if v is not None}


def dispatch(
    tool: str,
    run: Callable[[int], tuple[dict[str, Any], dict[str, Any]]],
    *,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shared cross-cutting logic for every `kb.*` tool (M1, M4, M5, M6 of 03-INTERFACES.md §6.2).

    `run` receives the resolved per-tool timeout and returns `(data, meta_extra)` — `meta_extra`
    carries tool-specific meta fields (e.g. `kb.search`'s `strategy_used`/`provenance`, WP06 §2).
    `args` (the call's arguments) and a summary of the result go to the invocation log,
    which `kbase usage` reads.
    AppErrors become a `ToolError` the model can read and react to; anything else is left
    to propagate so the SDK logs the traceback and reports a generic failure (M3).
    """
    config = _current_config()
    check_allowlisted(config, tool)
    timeout_s = resolve_timeout_s(config, tool)
    call = args or {}
    started = perf_counter()
    try:
        data, meta_extra = run(timeout_s)
    except AppError as exc:
        _record(
            config,
            tool,
            call,
            started,
            status="error",
            error_code=exc.code,
            error_message=exc.message,
        )
        raise ToolError(exc.message) from exc
    except Exception:
        _record(
            config,
            tool,
            call,
            started,
            status="error",
            error_code="INTERNAL_ERROR",
            error_message=None,
        )
        raise
    payload, truncated = truncate_data(data, config.max_result_bytes)
    _record(
        config,
        tool,
        call,
        started,
        status="ok",
        error_code=None,
        error_message=None,
        result={
            **summarize_result(data, meta_extra.get("provenance")),
            "truncated": truncated,
        },
    )
    return {"ok": True, "data": payload, "meta": {"truncated": truncated, **meta_extra}}


def _record(
    config: McpServerConfig,
    tool: str,
    args: dict[str, Any],
    started: float,
    *,
    status: str,
    error_code: str | None,
    error_message: str | None,
    result: dict[str, Any] | None = None,
) -> None:
    duration_ms = int((perf_counter() - started) * 1000)
    record_tool_invocation(
        ToolInvocation(
            id=new_id(),
            ts=utc_now(),
            server=config.name,
            tool=tool,
            args=args,
            status=status,
            duration_ms=duration_ms,
            error_code=error_code,
            error_message=error_message,
            caller=caller(),
            result=result,
        )
    )
