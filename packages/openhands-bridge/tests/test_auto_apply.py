"""WP08g: the bridge writes the agent's edits to the real repo at the end of each
turn, and an undo reaches the real repo too. Real WebSocket + real git working
copy, fake `AgentSession`: no Docker, no LLM."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from openhands_adapter.working_copy import WorkingCopy
from openhands_bridge import server as srv
from websockets.asyncio.client import ClientConnection, connect
from websockets.asyncio.server import serve

from openhands_adapter import ConversationStateUpdateEvent


@dataclass
class _Result:
    exit_code: int
    stdout: str
    stderr: str


@dataclass
class _Download:
    success: bool


class _LocalWorkspace:
    def __init__(self, root: Path) -> None:
        self.root = root

    def execute_command(self, command: str, timeout: float = 30.0) -> _Result:
        # The fixture has already populated the copy.
        command = command.replace("cp -a /workspace/source/. .", "true")
        proc = subprocess.run(
            ["bash", "-c", command],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return _Result(proc.returncode, proc.stdout, proc.stderr)

    def file_upload(self, source: str, dest: str) -> _Download:
        shutil.copyfile(source, dest)
        return _Download(True)

    def file_download(self, source: str, dest: str) -> _Download:
        if not Path(source).is_file():
            return _Download(False)
        shutil.copyfile(source, dest)
        return _Download(True)


@dataclass
class _Harness:
    host: Path
    copy: Path
    # One callable per user message: what "the agent" does to the copy.
    edits: list[Callable[[Path], None]] = field(default_factory=list)


def _fake_session_type(harness: _Harness, *, read_only: bool) -> type:
    class FakeSession:
        run_timeout_s = 10
        context_window = 1
        llm_source = "fake"

        def __init__(self, **kwargs: Any) -> None:
            self._callbacks = kwargs["callbacks"]
            self.project_path = Path(kwargs["project_path"])
            self.read_only = read_only
            self.working_copy = WorkingCopy(_LocalWorkspace(harness.copy), str(harness.copy))  # type: ignore[arg-type]
            self.workspace = SimpleNamespace()
            stats = SimpleNamespace(
                accumulated_token_usage=None, token_usages=[], accumulated_cost=0.0
            )
            self.conversation = SimpleNamespace(
                id="fake",
                state=SimpleNamespace(
                    events=[],
                    refresh_from_server=lambda: {"execution_status": "running"},
                ),
                conversation_stats=SimpleNamespace(get_combined_metrics=lambda: stats),
            )

        def final_text(self) -> str:
            return ""

        def __enter__(self) -> FakeSession:
            self.working_copy.initialize()
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def send(self, _text: str, *, blocking: bool = True) -> None:
            harness.edits.pop(0)(harness.copy)

            def finish() -> None:
                event = ConversationStateUpdateEvent(key="execution_status", value="finished")
                for callback in self._callbacks:
                    callback(event)

            threading.Thread(target=finish).start()

    return FakeSession


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def harness(tmp_path: Path) -> _Harness:
    host = tmp_path / "host"
    host.mkdir()
    (host / "app.py").write_text("v1\n")
    _git(host, "init", "-q", "-b", "main")
    _git(host, "add", "-A")
    _git(host, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    copy = tmp_path / "copy"
    shutil.copytree(host, copy)
    return _Harness(host=host, copy=copy)


async def _serve(
    monkeypatch: pytest.MonkeyPatch, harness: _Harness, *, read_only: bool = False
) -> AsyncIterator[ClientConnection]:
    monkeypatch.setattr(srv, "reap_orphan_sandboxes", lambda _keep=None: [])
    monkeypatch.setattr(
        srv,
        "load_openhands_config",
        lambda: SimpleNamespace(llm=SimpleNamespace(stream=False)),
    )
    monkeypatch.setattr(srv, "build_mcp_config", lambda _selected, _config: ({}, []))
    monkeypatch.setattr(srv.memory, "recall_context", lambda _text: None)
    monkeypatch.setattr(srv.memory, "record_episode", lambda _draft, ended_at: None)
    monkeypatch.setattr(srv, "AgentSession", _fake_session_type(harness, read_only=read_only))
    async with serve(srv._handle_connection, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        async with connect(f"ws://127.0.0.1:{port}") as ws:
            await ws.send(json.dumps({"type": "hello", "protocol": 2, "client": "test"}))
            await ws.send(json.dumps({"type": "start_session", "project_path": str(harness.host)}))
            await _until(ws, "session_started")
            yield ws


async def _until(ws: ClientConnection, wanted: str) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    while True:
        message = json.loads(await ws.recv())
        seen.append(message)
        if message["type"] == "error":
            pytest.fail(f"bridge error: {message}")
        if message["type"] == wanted:
            return seen


async def _turn(ws: ClientConnection) -> list[dict[str, Any]]:
    await ws.send(json.dumps({"type": "user_message", "text": "go"}))
    return await _until(ws, "turn_finished")


@pytest.fixture
async def client(
    monkeypatch: pytest.MonkeyPatch, harness: _Harness
) -> AsyncIterator[ClientConnection]:
    async for ws in _serve(monkeypatch, harness):
        yield ws


def _edit_app(copy: Path) -> None:
    (copy / "app.py").write_text("v2\n")
    (copy / "pkg").mkdir()
    (copy / "pkg" / "new.py").write_text("x\n")


async def test_turn_end_writes_edits_to_the_real_repo(
    client: ClientConnection, harness: _Harness
) -> None:
    harness.edits.append(_edit_app)

    messages = await _turn(client)

    assert (harness.host / "app.py").read_text() == "v2\n"
    assert (harness.host / "pkg" / "new.py").read_text() == "x\n"
    applied = next(m for m in messages if m["type"] == "changes_applied")
    assert {e["path"] for e in applied["applied"]} == {"app.py", "pkg/new.py"}
    types = [m["type"] for m in messages]
    assert types.index("changes_applied") < types.index("turn_finished")


async def test_a_turn_without_edits_sends_no_applied_message(
    client: ClientConnection, harness: _Harness
) -> None:
    harness.edits.append(lambda _copy: None)

    messages = await _turn(client)

    assert "changes_applied" not in [m["type"] for m in messages]


async def test_undo_reverts_the_real_repo(client: ClientConnection, harness: _Harness) -> None:
    harness.edits.append(_edit_app)
    messages = await _turn(client)
    checkpoint = next(m for m in messages if m["type"] == "checkpoint")["checkpoint_id"]

    await client.send(json.dumps({"type": "restore_checkpoint", "checkpoint_id": checkpoint}))
    await _until(client, "files_changed")

    assert (harness.host / "app.py").read_text() == "v1\n"
    assert not (harness.host / "pkg").exists()


async def test_conflict_is_skipped_stays_pending_then_can_be_overwritten(
    client: ClientConnection, harness: _Harness
) -> None:
    def edit_while_the_user_does(copy: Path) -> None:
        (harness.host / "app.py").write_text("edited by the user\n")
        _edit_app(copy)

    harness.edits.append(edit_while_the_user_does)

    messages = await _turn(client)

    assert (harness.host / "app.py").read_text() == "edited by the user\n"
    applied = next(m for m in messages if m["type"] == "changes_applied")
    assert [e["path"] for e in applied["skipped"]] == ["app.py"]
    assert (harness.host / "pkg" / "new.py").exists()

    await client.send(json.dumps({"type": "apply_changes", "paths": ["app.py"], "force": True}))
    await _until(client, "files_changed")

    assert (harness.host / "app.py").read_text() == "v2\n"


async def test_read_only_session_never_writes(
    monkeypatch: pytest.MonkeyPatch, harness: _Harness
) -> None:
    harness.edits.append(_edit_app)
    async for ws in _serve(monkeypatch, harness, read_only=True):
        messages = await _turn(ws)

        assert (harness.host / "app.py").read_text() == "v1\n"
        assert "changes_applied" not in [m["type"] for m in messages]


async def test_an_edit_between_turns_reaches_the_copy_and_is_not_a_conflict(
    client: ClientConnection, harness: _Harness
) -> None:
    seen: list[str] = []
    harness.edits.append(lambda _copy: None)
    await _turn(client)
    (harness.host / "app.py").write_text("edited by the user\n")
    harness.edits.append(lambda copy: seen.append((copy / "app.py").read_text()))
    harness.edits.append(lambda copy: (copy / "app.py").write_text("edited by the agent\n"))

    await _turn(client)
    messages = await _turn(client)

    assert seen == ["edited by the user\n"]
    assert (harness.host / "app.py").read_text() == "edited by the agent\n"
    applied = next(m for m in messages if m["type"] == "changes_applied")
    assert applied["skipped"] == []


async def test_a_secret_edited_on_the_host_never_enters_the_copy(
    client: ClientConnection, harness: _Harness
) -> None:
    (harness.host / ".env").write_text("TOKEN=x\n")
    subprocess.run(["git", "add", "-f", ".env"], cwd=harness.host, check=True)
    harness.edits.append(lambda _copy: None)

    await _turn(client)

    assert not (harness.copy / ".env").exists()
