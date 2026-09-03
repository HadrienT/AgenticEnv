from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from qmharness_mcp.schemas import McpServerConfig
from qmharness_mcp.tools import compare, dispatch, explain_failure, list_cases, run

_DESCRIPTIONS: dict[str, str] = {
    "qm.run": "Runs one check family bundle (quick/standard/full) and returns the report.",
    "qm.compare": "Diffs two already-produced RunReports; refuses if builds aren't comparable.",
    "qm.list_cases": "Lists available cases by product and family, without running anything.",
    "qm.explain_failure": "Full detail of one case: observed/expected/diff/message.",
}

_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "qm.run": run.run,
    "qm.compare": compare.compare,
    "qm.list_cases": list_cases.list_cases,
    "qm.explain_failure": explain_failure.explain_failure,
}


def build_server(config: McpServerConfig) -> MCPServer:
    """Registers only the tools listed in `config.tools_allowlist` (M1/M8 boundary)."""
    dispatch.init(config)
    server = MCPServer(config.name)
    for name, handler in _HANDLERS.items():
        if name in config.tools_allowlist:
            server.tool(name=name, description=_DESCRIPTIONS[name])(handler)
    return server


def main() -> None:
    from corelib.config import load_yaml_config

    config = load_yaml_config("mcp/qmharness.yaml", McpServerConfig)
    server = build_server(config)
    if config.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport=config.transport, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
