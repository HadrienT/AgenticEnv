"""Reads `configs/mcp/*.yaml`: what the client's picker lists, and what the agent
actually gets (WP12 §1).

Knowledge servers (`host_http`) run on the host and the sandbox calls them over
HTTP. Code servers (`sandbox_stdio`) run inside the sandbox, because they must see
the copy the agent is editing: they need the image from `infra/docker/agent`.
"""

from __future__ import annotations

import socket
from typing import Literal

import yaml
from corelib.config import get_settings, repo_root
from corelib.errors import ConfigError
from corelib.mcp_http import mcp_token
from pydantic import BaseModel, ConfigDict

from openhands_adapter import OpenHandsConfig

_SANDBOX_REPO = "/opt/agenticenv"


class McpServerSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    transport: str
    tools_allowlist: list[str] = []
    reach: Literal["host_http", "sandbox_stdio"] = "host_http"
    port: int = 0


def _sandbox_env() -> dict[str, str]:
    """`corelib` needs its settings even where no database or LLM is reachable."""
    return {
        "AGX_ENV": "dev",
        "AGX_REPO_ROOT": _SANDBOX_REPO,
        "AGX_DB_HOST": "127.0.0.1",
        "AGX_DB_PORT": "5432",
        "AGX_DB_NAME": "unused",
        "AGX_DB_USER": "unused",
        "AGX_DB_PASSWORD": "unused",
        "AGX_LLM_BASE_URL": "http://127.0.0.1:8000/v1",
        "AGX_LLM_SERVED_MODEL": "unused",
        "AGX_LLM_CTX_SIZE": "1",
        "AGX_PATHS_MODELS_DIR": "/tmp",
        "AGX_PATHS_DOCUMENTS_DIR": "/tmp",
        "AGX_PATHS_REPOS_DIR": "/workspace",
    }


def _is_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def unavailable_reason(server: McpServerSummary, config: OpenHandsConfig) -> str | None:
    """Why a session could not use `server` right now, or None if it can."""
    if server.reach == "host_http":
        if not _is_listening(config.mcp.bind_host, server.port):
            return "server not running"
        return None
    return None if config.sandbox.code_tools else "needs code_tools in configs/openhands.yaml"


def build_mcp_config(
    selected: list[str], config: OpenHandsConfig
) -> tuple[dict[str, object], list[str]]:
    """`(mcp_config, unavailable)`: the servers the agent gets, and the ones it was
    meant to get but can't reach. Nothing selected means all of them; a server that
    is down must not cost the session its other tools."""
    servers: dict[str, object] = {}
    unavailable: list[str] = []
    for server in list_mcp_servers():
        if selected and server.name not in selected:
            continue
        if unavailable_reason(server, config) is not None:
            unavailable.append(server.name)
        elif server.reach == "host_http":
            servers[server.name] = {
                "url": f"http://{config.mcp.sandbox_host}:{server.port}/mcp",
                "headers": {"Authorization": f"Bearer {mcp_token()}"},
            }
        else:
            servers[server.name] = {
                "command": f"{_SANDBOX_REPO}/.venv/bin/{server.name}-mcp",
                "env": _sandbox_env(),
            }
    return ({"mcpServers": servers} if servers else {}), unavailable


def list_mcp_servers() -> list[McpServerSummary]:
    mcp_dir = repo_root() / get_settings().configs_dir / "mcp"
    if not mcp_dir.is_dir():
        raise ConfigError(
            f"MCP config directory not found: {mcp_dir}", details={"path": str(mcp_dir)}
        )

    servers: list[McpServerSummary] = []
    for path in sorted(mcp_dir.glob("*.yaml")):
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        servers.append(McpServerSummary.model_validate(raw))
    return servers
