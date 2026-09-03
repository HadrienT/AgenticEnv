from __future__ import annotations

import json
from typing import Any

from corelib.errors import PermissionDeniedError

from kbase_mcp.schemas import McpServerConfig


def check_allowlisted(config: McpServerConfig, tool: str) -> None:
    """M1/M8-adjacent guard: a server never executes a tool it wasn't configured to expose."""
    if tool not in config.tools_allowlist:
        raise PermissionDeniedError(
            f"tool not allowlisted for this server profile: {tool}", details={"tool": tool}
        )


def resolve_timeout_s(config: McpServerConfig, tool: str) -> int:
    """M4: every tool has a timeout, defaulting to the server-wide value."""
    return config.per_tool_timeout_s.get(tool, config.default_timeout_s)


def truncate_data(
    data: dict[str, Any] | None, max_bytes: int
) -> tuple[dict[str, Any] | None, bool]:
    """M5: results beyond `max_result_bytes` are truncated, never silently dropped."""
    if data is None:
        return None, False
    encoded = json.dumps(data)
    if len(encoded.encode("utf-8")) <= max_bytes:
        return data, False
    return {"truncated": True, "original_bytes": len(encoded.encode("utf-8"))}, True
