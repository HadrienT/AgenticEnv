from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

from corelib.mcp_http import BearerAuth, mcp_token


async def _call(token_sent: str | None) -> tuple[int, bool]:
    reached = False
    sent: list[dict[str, Any]] = []

    async def app(_scope: Any, _receive: Any, send: Any) -> None:
        nonlocal reached
        reached = True
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    headers = [(b"authorization", token_sent.encode())] if token_sent else []
    await BearerAuth(app, "tok")({"type": "http", "headers": headers}, None, send)
    return sent[0]["status"], reached


async def test_valid_token_reaches_the_app() -> None:
    assert await _call("Bearer tok") == (200, True)


async def test_missing_or_wrong_token_never_reaches_the_app() -> None:
    assert await _call(None) == (401, False)
    assert await _call("Bearer nope") == (401, False)


def test_token_is_private_and_stable(tmp_path: Path) -> None:
    path = tmp_path / "state" / "mcp.token"

    first = mcp_token(path)

    assert mcp_token(path) == first
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
