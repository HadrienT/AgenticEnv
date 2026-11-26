from __future__ import annotations

import asyncio
from typing import Any

from kbase_mcp.schemas import McpServerConfig
from kbase_mcp.server import _HANDLERS, build_server


def _schemas() -> dict[str, dict[str, Any]]:
    config = McpServerConfig.model_validate({"name": "kbase", "tools_allowlist": list(_HANDLERS)})
    tools = asyncio.run(build_server(config).list_tools())
    out: dict[str, dict[str, Any]] = {}
    for tool in tools:
        dumped = tool.model_dump()
        out[dumped["name"]] = dumped.get("inputSchema") or dumped["input_schema"]
    return out


def test_every_tool_parameter_is_explained() -> None:
    # Explaining parameters is what raises an MCP tool's selection and correct use
    # (arXiv 2610.14334, 2602.14878): the agent sees only the JSON schema.
    missing = [
        f"{name}.{param}"
        for name, schema in _schemas().items()
        for param, spec in schema.get("properties", {}).items()
        if not spec.get("description")
    ]
    assert missing == []


def test_search_parameter_descriptions_stay_short() -> None:
    # Richer descriptions cost the agent steps and tokens on every call (2602.14878).
    lengths = {p: len(s["description"]) for p, s in _schemas()["kb.search"]["properties"].items()}
    assert max(lengths.values()) <= 240, lengths
