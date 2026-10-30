"""Serving an MCP server over HTTP to the Docker sandbox (WP12 §1).

`stdio` stays the default in `configs/mcp/*.yaml`, for clients that start a server
themselves; the user units set `AGX_MCP_TRANSPORT=streamable-http`. Reachable from
the Docker bridge means reachable by any container on it, hence the bearer token.
"""

from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path
from typing import Any

from corelib.errors import ConfigError

Scope = dict[str, Any]


def _state_dir() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state_home) / "agenticenv"


def mcp_token(path: Path | None = None) -> str:
    """The token shared by the MCP servers and the bridge. Created once, and kept
    across restarts: each side starts on its own."""
    target = path or _state_dir() / "mcp.token"
    if target.is_file():
        return target.read_text().strip()
    token = secrets.token_urlsafe(32)
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return target.read_text().strip()
    except OSError as exc:
        raise ConfigError(
            f"cannot write the MCP token: {exc}", details={"path": str(target)}
        ) from exc
    with os.fdopen(fd, "w") as handle:
        handle.write(token)
    return token


class BearerAuth:
    """ASGI middleware: no valid `Authorization` header, no MCP."""

    def __init__(self, app: Any, token: str) -> None:
        self._app = app
        self._expected = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        if hmac.compare_digest(headers.get(b"authorization", b""), self._expected):
            await self._app(scope, receive, send)
            return
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": b"invalid or missing MCP token\n"})


def run_server(server: Any, *, transport: str, host: str, port: int) -> None:
    """Runs `server` the way the environment asks, over the configured default."""
    transport = os.environ.get("AGX_MCP_TRANSPORT", transport)
    if transport == "stdio":
        server.run(transport="stdio")
        return

    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    # The DNS-rebinding check is for browsers, which the token already shuts out,
    # and it would refuse `host.docker.internal`.
    app = server.streamable_http_app(
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    uvicorn.run(
        BearerAuth(app, mcp_token()),
        host=os.environ.get("AGX_MCP_HOST", host),
        port=int(os.environ.get("AGX_MCP_PORT", port)),
        log_level="warning",
    )
