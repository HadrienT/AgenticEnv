from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from codeintel_mcp.schemas import McpServerConfig
from codeintel_mcp.tools import (
    callgraph,
    definition,
    diff_context,
    dispatch,
    find_symbol,
    grep,
    implementations,
    includes,
    outline,
    references,
    registry_matrix,
    signature,
)

_DESCRIPTIONS: dict[str, str] = {
    "code.find_symbol": "Fuzzy project-wide symbol search, returning file:line matches.",
    "code.definition": "Signature + doc of a symbol; body only if `include_body=true`.",
    "code.references": "Every call/use site of a symbol, exhaustive on `total_found`.",
    "code.implementations": "Every override/derived class of a symbol (e.g. an interface).",
    "code.outline": "A file's classes/methods/signatures, never function bodies.",
    "code.signature": "The exact signature of a symbol, without reading the file.",
    "code.callers": "Who calls a function, bounded call-hierarchy depth.",
    "code.callees": "What a function calls, bounded call-hierarchy depth.",
    "code.includes": "The #include graph of a file, in one direction.",
    "code.grep": "Text search that can exclude comments/string literals.",
    "code.registry_matrix": "The real (instrument, model, engine) registration matrix.",
    "code.diff_context": "Symbols impacted by a git diff, with reference counts.",
}

_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "code.find_symbol": find_symbol.find_symbol,
    "code.definition": definition.definition,
    "code.references": references.references,
    "code.implementations": implementations.implementations,
    "code.outline": outline.outline,
    "code.signature": signature.signature,
    "code.callers": callgraph.callers,
    "code.callees": callgraph.callees,
    "code.includes": includes.includes,
    "code.grep": grep.grep,
    "code.registry_matrix": registry_matrix.registry_matrix,
    "code.diff_context": diff_context.diff_context,
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

    config = load_yaml_config("mcp/codeintel.yaml", McpServerConfig)
    server = build_server(config)
    if config.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport=config.transport, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
