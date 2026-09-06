"""Reads `configs/mcp/*.yaml` for the pre-session MCP picker.

Phase 1 (see blueprint/wp/WP08b-openhands-sandbox.md): this only lists what's
*configured* on the host, for the client's UI. It does not yet make any MCP
server reachable from inside the Docker sandbox -- that needs the
`streamable-http` bridge described as Phase 2 in the same doc. A server picked
here and passed back as `StartSession.mcp_servers` is accepted but currently
has no effect on the agent's actual tool access.
"""

from __future__ import annotations

import yaml
from corelib.config import get_settings
from corelib.errors import ConfigError
from pydantic import BaseModel, ConfigDict


class McpServerSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    transport: str
    tools_allowlist: list[str] = []


def list_mcp_servers() -> list[McpServerSummary]:
    mcp_dir = get_settings().configs_dir / "mcp"
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
