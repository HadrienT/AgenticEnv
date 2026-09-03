from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from cppdev_mcp.schemas import McpServerConfig
from cppdev_mcp.tools import (
    analyze,
    bench,
    build,
    coverage,
    dispatch,
    format,
    sanitize,
    targets,
    test,
)

_DESCRIPTIONS: dict[str, str] = {
    "cpp.configure": "Run cmake --preset <preset> for the target C++ project.",
    "cpp.build": "Build a CMake target (or all) with an optional clean rebuild.",
    "cpp.test": "Run ctest against an already-configured build directory.",
    "cpp.targets": "List CMake presets, build targets, and configure state.",
    "cpp.format_check": "Check clang-format compliance without rewriting files.",
    "cpp.tidy": "Run clang-tidy static analysis over the given source paths.",
    "cpp.sanitize": "Run an ASan/UBSan-instrumented binary and parse its findings.",
    "cpp.coverage": "Collect gcovr line/function coverage for a build directory.",
    "cpp.bench": "Run a Google Benchmark binary and compare against a reference.",
}

_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "cpp.configure": build.configure,
    "cpp.build": build.build,
    "cpp.test": test.test,
    "cpp.targets": targets.targets,
    "cpp.format_check": format.format_check,
    "cpp.tidy": analyze.tidy,
    "cpp.sanitize": sanitize.sanitize,
    "cpp.coverage": coverage.coverage,
    "cpp.bench": bench.bench,
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

    config = load_yaml_config("mcp/cppdev.yaml", McpServerConfig)
    server = build_server(config)
    if config.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport=config.transport, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
