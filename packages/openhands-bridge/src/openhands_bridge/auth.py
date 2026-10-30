"""Who may talk to the bridge (WP10 §1).

A local port is no boundary: any web page open in a browser on this machine can
reach `ws://127.0.0.1`, and the bridge writes to real repos. So a connection needs
the token only a process of this user can read, and browsers are refused outright:
they always send an `Origin`, the extension host (Node) never does.
"""

from __future__ import annotations

import hmac
import http
import os
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

from corelib.errors import ConfigError, ValidationError
from websockets.asyncio.server import ServerConnection
from websockets.http11 import Request, Response

_FORBIDDEN_ROOTS = ("/", "/bin", "/boot", "/dev", "/etc", "/lib", "/proc", "/root", "/sbin", "/sys")
_FORBIDDEN_ROOTS_DEEP = ("/usr", "/var")


def token_path() -> Path:
    # Stable whatever the launcher: a systemd user unit and a VS Code extension
    # host don't reliably share XDG_RUNTIME_DIR, and agenticenv-chat reads this too.
    state_home = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state_home) / "agenticenv" / "bridge.token"


def ensure_token(path: Path | None = None) -> str:
    """A fresh token at each bridge start, readable by this user only."""
    target = path or token_path()
    token = secrets.token_urlsafe(32)
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.unlink(missing_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(token)
    except OSError as exc:
        raise ConfigError(
            f"cannot write the bridge token: {exc}", details={"path": str(target)}
        ) from exc
    return token


def _require_token(token: str) -> Callable[[ServerConnection, Request], Response | None]:
    expected = f"Bearer {token}".encode()

    def check(connection: ServerConnection, request: Request) -> Response | None:
        supplied = request.headers.get("Authorization", "").encode()
        if hmac.compare_digest(supplied, expected):
            return None
        return connection.respond(http.HTTPStatus.UNAUTHORIZED, "invalid or missing bridge token\n")

    return check


def serve_options(token: str) -> dict[str, Any]:
    # `None` is "no Origin header": the only origin a non-browser client has.
    return {"origins": [None], "process_request": _require_token(token)}


def validate_project_path(raw: str) -> str:
    """The folder a session may copy from and write back to: a real project, not a
    system tree or the whole home directory."""
    path = Path(raw).expanduser().resolve()
    as_text = str(path)
    deep = any(as_text == r or as_text.startswith(f"{r}/") for r in _FORBIDDEN_ROOTS_DEEP)
    if not path.is_dir() or as_text in _FORBIDDEN_ROOTS or deep or path == Path.home().resolve():
        raise ValidationError(
            f"not an allowed project folder: {as_text}", details={"project_path": as_text}
        )
    return as_text
