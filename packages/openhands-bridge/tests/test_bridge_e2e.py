"""Full-system smoke test: the bridge itself, over a real WebSocket connection,
against a real Docker sandbox + llama-server. Not run in CI -- same
prerequisites as packages/openhands_adapter/tests/test_session_e2e.py, run
manually with `uv run pytest packages/openhands-bridge -m e2e -q`.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from openhands_bridge.server import _handle_connection
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

pytestmark = pytest.mark.e2e


@pytest_asyncio.fixture
async def bridge_url() -> AsyncIterator[str]:
    async with serve(_handle_connection, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A minimal git repo to bind-mount READ-ONLY as the sandbox source (WP08d).
    The agent works on a disposable copy; `apply_changes` is what writes back.
    World-writable so the `cp -a` copy the agent-server (uid 10001) makes is
    itself writable."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# sample\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["chmod", "-R", "0777", str(tmp_path)], check=True)
    return tmp_path


async def test_chat_round_trip_over_websocket(bridge_url: str, project: Path) -> None:
    """Deliberately a *trivial* turn (no file edit): the agent making real tool
    calls on this local 30B is minutes-slow and, when llama-server is shared
    with another live session, blows any reasonable timeout. A "just answer"
    turn keeps this a fast, reliable smoke of the whole pipe -- session start
    with a bind-mounted project, streamed reply, and the `files_changed`
    filter. The "agent actually edits the mounted repo" path is verified
    manually (see WP08c §"Fichiers modifiés")."""
    async with connect(bridge_url) as ws:
        await ws.send(json.dumps({"type": "hello", "protocol": 2, "client": "e2e/0"}))
        welcome = json.loads(await ws.recv())
        assert welcome["type"] == "welcome"
        assert welcome["protocol"] == 2
        assert "apply" in welcome["capabilities"]

        await ws.send(json.dumps({"type": "start_session", "project_path": str(project)}))
        started = json.loads(await ws.recv())
        assert started["type"] == "session_started"
        assert started["llm_source"] in {"create_payload", "switch_llm"}
        assert started["mode"] == "agent"

        await ws.send(
            json.dumps({"type": "user_message", "text": "Réponds exactement : TEST_FINAL"})
        )

        saw_final_text = False
        saw_turn_started = False
        turn_finished_reason: str | None = None
        files_changed: list[dict[str, str]] | None = None
        saw_usage = False
        seqs: list[int] = []
        async with asyncio.timeout(900):
            while turn_finished_reason is None:
                message = json.loads(await ws.recv())
                if "seq" in message and message["seq"] is not None:
                    seqs.append(message["seq"])
                if message["type"] == "turn_started":
                    saw_turn_started = True
                elif message["type"] == "event":
                    content = message["event"].get("llm_message", {}).get("content", [])
                    if any("TEST_FINAL" in b.get("text", "") for b in content):
                        saw_final_text = True
                elif message["type"] == "files_changed":
                    files_changed = message["changes"]
                elif message["type"] == "usage":
                    saw_usage = True
                    assert message["accumulated_cost"] >= 0.0
                elif message["type"] == "turn_finished":
                    turn_finished_reason = message["reason"]
                elif message["type"] == "awaiting_confirmation":
                    await ws.send(json.dumps({"type": "confirm_action", "accept": True}))

        assert saw_turn_started
        assert turn_finished_reason == "completed"
        assert saw_usage
        assert seqs == sorted(seqs) and seqs == list(range(seqs[0], seqs[0] + len(seqs)))
        assert saw_final_text
        # A "just answer" turn changes nothing; and crucially the agent-server's
        # own workspace internals never leak into the list.
        assert files_changed == [], files_changed
