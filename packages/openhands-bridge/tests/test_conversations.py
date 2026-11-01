"""WP08e: conversations outlive their connection. Real WebSocket, fake sandbox."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from openhands_bridge import conversations
from openhands_bridge import server as srv
from websockets.asyncio.client import ClientConnection, connect
from websockets.asyncio.server import serve

from openhands_adapter import ConversationStateUpdateEvent


class _Fake:
    def __init__(self) -> None:
        self.sandboxes: list[Any] = []
        self.persistent = True
        self.finish_turns = True


def _session_type(fake: _Fake) -> type:
    class FakeSession:
        run_timeout_s = 600
        context_window = 1
        llm_source = "fake"
        working_copy = None

        def __init__(self, **kwargs: Any) -> None:
            self.callbacks = kwargs["callbacks"]
            project_path = kwargs.get("project_path")
            self.project_path = Path(project_path) if project_path else None
            self.read_only = kwargs.get("read_only", False)
            self.first_id = kwargs.get("conversation_id")
            self.exited = False
            self.opened: list[str] = []
            self.workspace = SimpleNamespace(git_changes=lambda _path: [])
            self.conversation: Any = None
            fake.sandboxes.append(self)

        def _status(self, value: str) -> None:
            for callback in self.callbacks:
                callback(ConversationStateUpdateEvent(key="execution_status", value=value))

        def open_conversation(self, conversation_id: str | None = None) -> str:
            conversation_id = conversation_id or uuid.uuid4().hex
            self.opened.append(conversation_id)
            stats = SimpleNamespace(
                accumulated_token_usage=None, token_usages=[], accumulated_cost=0.0
            )
            self.conversation = SimpleNamespace(
                id=conversation_id,
                state=SimpleNamespace(
                    events=[], refresh_from_server=lambda: {"execution_status": "running"}
                ),
                conversation_stats=SimpleNamespace(get_combined_metrics=lambda: stats),
                pause=lambda: self._status("paused"),
                reject_pending_actions=lambda: None,
            )
            return conversation_id

        def final_text(self) -> str:
            return ""

        def fall_back_to_green(self) -> list[str]:
            return []

        def __enter__(self) -> Any:
            self.open_conversation(self.first_id)
            return self

        def __exit__(self, *_: object) -> None:
            self.exited = True

        def send(self, _text: str, *, blocking: bool = True) -> None:
            if fake.finish_turns:
                self._status("finished")

    return FakeSession


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Fake:
    state = _Fake()
    config = SimpleNamespace(
        llm=SimpleNamespace(stream=False),
        sandbox=SimpleNamespace(persistent_conversations=True),
    )
    monkeypatch.setattr(conversations, "persistence_dir", lambda: tmp_path)
    monkeypatch.setattr(srv, "reap_orphan_sandboxes", lambda _keep=None: [])
    monkeypatch.setattr(srv, "load_openhands_config", lambda: config)
    monkeypatch.setattr(srv, "build_mcp_config", lambda _selected, _config: ({}, []))
    monkeypatch.setattr(srv, "validate_project_path", str)
    monkeypatch.setattr(srv, "_snapshot_host_tree", lambda _root: {})
    monkeypatch.setattr(srv.memory, "recall_context", lambda _text: None)
    monkeypatch.setattr(srv.memory, "record_episode", lambda _draft, ended_at: None)
    monkeypatch.setattr(srv, "AgentSession", _session_type(state))
    monkeypatch.setattr(srv, "_CANCEL_GRACE_S", 0.1)
    monkeypatch.setattr(srv, "_session_owner", None)
    monkeypatch.setattr(srv, "_sandbox", None)
    return state


@pytest_asyncio.fixture
async def url(fake: _Fake) -> AsyncIterator[str]:
    async with serve(srv._handle_connection, "127.0.0.1", 0) as server:
        yield f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"


async def _send(ws: ClientConnection, **message: Any) -> None:
    await ws.send(json.dumps(message))


async def _until(ws: ClientConnection, wanted: str) -> dict[str, Any]:
    while True:
        message = json.loads(await asyncio.wait_for(ws.recv(), 10))
        if message["type"] == wanted:
            return message


async def _start(ws: ClientConnection, **fields: Any) -> str:
    await _send(ws, type="start_session", **fields)
    return (await _until(ws, "session_started"))["conversation_id"]


async def _turn(ws: ClientConnection) -> int:
    await _send(ws, type="user_message", text="first message")
    return (await _until(ws, "turn_finished"))["seq"]


async def _gone(condition: Any) -> None:
    for _ in range(200):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("never happened")


async def test_resume_is_offered_only_when_turned_on(url: str, fake: _Fake) -> None:
    async with connect(url) as ws:
        await _send(ws, type="hello", client="t", protocol=2)
        assert "resume" in (await _until(ws, "welcome"))["capabilities"]

    srv.load_openhands_config().sandbox.persistent_conversations = False
    async with connect(url) as ws:
        await _send(ws, type="hello", client="t", protocol=2)
        assert "resume" not in (await _until(ws, "welcome"))["capabilities"]


async def test_a_reconnect_gets_the_same_sandbox_and_what_it_missed(url: str, fake: _Fake) -> None:
    async with connect(url) as ws:
        conversation = await _start(ws)
        started_seq = 1
        last = await _turn(ws)

    await _gone(lambda: srv._session_owner is None)
    assert not fake.sandboxes[0].exited

    async with connect(url) as ws:
        await _send(ws, type="resume", conversation_id=conversation, last_seq=started_seq)
        replayed = []
        while True:
            message = json.loads(await asyncio.wait_for(ws.recv(), 10))
            if message["type"] == "resumed":
                break
            replayed.append(message)

        assert message["seq"] > last
        assert replayed[-1]["type"] == "turn_finished"
        assert all(item["seq"] > started_seq for item in replayed)
        assert await _turn(ws) > message["seq"]
    assert len(fake.sandboxes) == 1


async def test_conversations_share_a_sandbox_and_keep_their_own_numbers(
    url: str, fake: _Fake
) -> None:
    async with connect(url) as ws:
        first = await _start(ws)
        first_seq = await _turn(ws)
        second = await _start(ws)

        await _send(ws, type="list_conversations")
        items = (await _until(ws, "conversations"))["items"]
        assert {item["conversation_id"] for item in items} == {first, second}
        assert [i["conversation_id"] for i in items if i["active"]] == [second]

        await _send(ws, type="resume", conversation_id=first, last_seq=first_seq)
        assert (await _until(ws, "resumed"))["seq"] == first_seq + 1

    assert len(fake.sandboxes) == 1
    assert fake.sandboxes[0].opened == [first, second, first]


async def test_switching_ends_the_running_turn(url: str, fake: _Fake) -> None:
    fake.finish_turns = False
    async with connect(url) as ws:
        await _start(ws)
        await _send(ws, type="user_message", text="go")
        await _until(ws, "turn_started")

        await _send(ws, type="start_session")
        assert (await _until(ws, "turn_finished"))["reason"] == "cancelled"
        await _until(ws, "session_started")


async def test_an_abandoned_sandbox_closes(
    url: str, fake: _Fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_SANDBOX_IDLE_S", 0.01)
    async with connect(url) as ws:
        await _start(ws)

    await _gone(lambda: fake.sandboxes[0].exited)
    assert srv._sandbox is None


async def test_a_returning_client_keeps_the_sandbox_from_closing(
    url: str, fake: _Fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_SANDBOX_IDLE_S", 0.2)
    async with connect(url) as ws:
        conversation = await _start(ws)
    await _gone(lambda: srv._session_owner is None)

    async with connect(url) as ws:
        await _send(ws, type="resume", conversation_id=conversation, last_seq=0)
        await _until(ws, "resumed")
        await asyncio.sleep(0.4)

        assert not fake.sandboxes[0].exited


async def test_resume_after_a_restart_reattaches_in_a_new_sandbox(url: str, fake: _Fake) -> None:
    async with connect(url) as ws:
        conversation = await _start(ws, project_path="/repo", profile="coding")
        last = await _turn(ws)
    await _gone(lambda: srv._session_owner is None)
    srv._sandbox = None  # what a new bridge process finds

    async with connect(url) as ws:
        await _send(ws, type="resume", conversation_id=conversation, last_seq=last)
        resumed = await _until(ws, "resumed")

    assert resumed["seq"] == last + 1
    assert fake.sandboxes[1].first_id == conversation
    assert str(fake.sandboxes[1].project_path) == "/repo"


async def test_another_project_replaces_an_abandoned_sandbox(url: str, fake: _Fake) -> None:
    async with connect(url) as ws:
        await _start(ws, project_path="/one")
    await _gone(lambda: srv._session_owner is None)

    async with connect(url) as ws:
        await _start(ws, project_path="/two")

    assert fake.sandboxes[0].exited
    assert len(fake.sandboxes) == 2


async def test_a_second_client_is_refused_while_the_first_stays(url: str, fake: _Fake) -> None:
    async with connect(url) as first, connect(url) as second:
        conversation = await _start(first)
        await _send(second, type="resume", conversation_id=conversation, last_seq=0)
        assert (await _until(second, "error"))["code"] == "SESSION_BUSY"


async def test_an_unknown_conversation_says_so(url: str, fake: _Fake) -> None:
    async with connect(url) as ws:
        await _send(ws, type="resume", conversation_id="nope", last_seq=0)
        assert (await _until(ws, "error"))["code"] == "UNKNOWN_CONVERSATION"


async def test_archiving_hides_a_conversation_but_not_the_active_one(url: str, fake: _Fake) -> None:
    async with connect(url) as ws:
        first = await _start(ws)
        second = await _start(ws)

        await _send(ws, type="archive_conversation", conversation_id=second)
        assert (await _until(ws, "error"))["code"] == "CONVERSATION_ACTIVE"

        await _send(ws, type="archive_conversation", conversation_id=first)
        items = (await _until(ws, "conversations"))["items"]
        assert [item["conversation_id"] for item in items] == [second]


async def test_without_the_option_nothing_is_kept(url: str, fake: _Fake, tmp_path: Path) -> None:
    srv.load_openhands_config().sandbox.persistent_conversations = False
    async with connect(url) as ws:
        await _start(ws)

    await _gone(lambda: fake.sandboxes[0].exited)
    assert not (tmp_path / "index.json").exists()
