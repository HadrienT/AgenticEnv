from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class McpServerConfig(BaseModel):
    """Loaded from `configs/mcp/qmharness.yaml`. See 06-CONFIG.md `configs/mcp/<server>.yaml`."""

    name: str = "qmharness"
    transport: Literal["stdio", "streamable-http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 8205
    default_timeout_s: int = 30
    max_result_bytes: int = 262_144
    tools_allowlist: list[str]
    per_tool_timeout_s: dict[str, int] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    details: dict[str, Any]
    retryable: bool


class ToolEnvelope(BaseModel):
    """The one response shape every tool returns (03-INTERFACES.md §6.1)."""

    ok: bool
    data: dict[str, Any] | None = None
    error: ErrorEnvelope | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
