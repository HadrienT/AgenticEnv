from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from agentmem_mcp.schemas import McpServerConfig
from agentmem_mcp.tools import dispatch, get_procedure, list_procedures, recall, remember

_DESCRIPTIONS: dict[str, str] = {
    "mem.recall": (
        "Find similar past episodes (goal/summary/lessons) before starting a task, so "
        "you don't repeat a known mistake. Returns summaries only, never the full action "
        'trace. Example: `recall(query="calibrate Heston on a vol surface", k=5)`.'
    ),
    "mem.remember": (
        "Persist one finished task as an immutable episode. Requires `confirm=true`. "
        "`summary` and `lessons` are mandatory and must be non-empty. Example: "
        '`remember(episode_id="task-42", task_id="task-42", agent_profile="quant", '
        'goal="...", started_at="2026-09-03T10:00:00Z", ended_at="2026-09-03T10:20:00Z", '
        'status="success", summary="...", lessons=["..."], confirm=true)`.'
    ),
    "mem.list_procedures": (
        "List available reusable procedures (recipes), optionally filtered by tags."
    ),
    "mem.get_procedure": (
        "Full steps of one procedure, by name (+ optional version, default latest)."
    ),
}

_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "mem.recall": recall.recall,
    "mem.remember": remember.remember,
    "mem.list_procedures": list_procedures.list_procedures,
    "mem.get_procedure": get_procedure.get_procedure,
}


def build_server(config: McpServerConfig) -> MCPServer:
    """Registers only the tools listed in `config.tools_allowlist` (M1/M8 boundary)."""
    dispatch.init(config)
    server = MCPServer(config.name)
    for name, handler in _HANDLERS.items():
        if name in config.tools_allowlist:
            server.tool(name=name, description=_DESCRIPTIONS[name])(handler)
    return server


def _check_embeddings_dimension(expected_dim: int) -> None:
    """Boot-time guard (mirrors kbase-mcp): refuse to start if `embeddings.dim` disagrees
    with the database's `vector(D)`. Never a warning — this is a CRITICAL misconfiguration."""
    from agentmem.episodic import assert_dimension_matches
    from corelib.db import session_scope
    from corelib.errors import ConfigError
    from corelib.logging import get_logger

    logger = get_logger(__name__)
    try:
        with session_scope() as session:
            assert_dimension_matches(session, expected_dim)
    except ConfigError as exc:
        logger.critical("refusing to start: %s", exc.message)
        raise SystemExit(1) from exc


def _sync_procedures_if_configured(source_dir: str, sync_on_start: bool) -> None:
    """A8: `sync_from_git` runs at boot when `procedural.sync_on_start` is set."""
    if not sync_on_start:
        return
    from pathlib import Path

    from agentmem.procedural import sync_from_git
    from corelib.logging import get_logger

    logger = get_logger(__name__)
    report = sync_from_git(Path.cwd(), source_dir=source_dir)
    logger.info(
        "procedures synced from git",
        extra={"synced": report.synced, "removed": report.removed, "errors": report.errors},
    )


def main() -> None:
    from agentmem.config import load_agentmem_config
    from corelib.config import load_yaml_config

    config = load_yaml_config("mcp/agentmem.yaml", McpServerConfig)
    agentmem_config = load_agentmem_config()
    _check_embeddings_dimension(agentmem_config.embeddings.dim)
    _sync_procedures_if_configured(
        agentmem_config.procedural.source_dir, agentmem_config.procedural.sync_on_start
    )
    server = build_server(config)
    if config.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport=config.transport, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
