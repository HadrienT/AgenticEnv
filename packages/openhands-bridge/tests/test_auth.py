"""WP10 §1: only a local process that can read the token gets in."""

from __future__ import annotations

import stat
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from corelib.errors import ConfigError, ValidationError
from openhands_bridge.auth import ensure_token, serve_options, validate_project_path
from websockets.asyncio.client import connect
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import InvalidStatus

_TOKEN = "s3cret"


async def _echo(ws: ServerConnection) -> None:
    await ws.send("in")


@pytest_asyncio.fixture
async def url() -> AsyncIterator[str]:
    async with serve(_echo, "127.0.0.1", 0, **serve_options(_TOKEN)) as server:
        yield f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"


async def test_valid_token_gets_in(url: str) -> None:
    async with connect(url, additional_headers={"Authorization": f"Bearer {_TOKEN}"}) as ws:
        assert await ws.recv() == "in"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
async def test_missing_or_wrong_token_is_refused(url: str, headers: dict[str, str]) -> None:
    with pytest.raises(InvalidStatus) as caught:
        async with connect(url, additional_headers=headers):
            pass
    assert caught.value.response.status_code == 401


async def test_a_browser_origin_is_refused_even_with_the_token(url: str) -> None:
    headers = {"Authorization": f"Bearer {_TOKEN}", "Origin": "https://evil.example"}
    with pytest.raises(InvalidStatus) as caught:
        async with connect(url, additional_headers=headers):
            pass
    assert caught.value.response.status_code == 403


def test_token_file_is_private_and_changes_at_each_start(tmp_path: Path) -> None:
    path = tmp_path / "state" / "bridge.token"

    first = ensure_token(path)
    second = ensure_token(path)

    assert first != second
    assert path.read_text() == second
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_unwritable_token_location_refuses_to_start(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")

    with pytest.raises(ConfigError):
        ensure_token(blocker / "bridge.token")


def test_a_project_folder_is_accepted(tmp_path: Path) -> None:
    assert validate_project_path(str(tmp_path)) == str(tmp_path.resolve())


@pytest.mark.parametrize("raw", ["/", "/etc", "/usr/local", "~", "/does/not/exist"])
def test_system_trees_and_home_are_refused(raw: str) -> None:
    with pytest.raises(ValidationError):
        validate_project_path(raw)
