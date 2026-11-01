"""WP11: the read loop stays free during a turn, and a turn always ends cleanly.
Real WebSocket, fake `AgentSession`: no Docker, no LLM."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from openhands.sdk import Message, TextContent
from openhands_bridge import server as srv
from websockets.asyncio.client import ClientConnection, connect
from websockets.asyncio.server import serve

from openhands_adapter import (
    STARTUP_STEPS,
    ConversationStateUpdateEvent,
    MessageEvent,
    StreamingDeltaEvent,
)


class _Fake:
    """What the fake agent does, and what the bridge asked of it."""

    def __init__(self) -> None:
        self.paused = threading.Event()
        self.exited = threading.Event()
        self.confirm_pause = True
        self.fail_send: Exception | None = None
        self.fail_stats = False
        self.sessions = 0
        self.calls: list[str] = []
        self.steps_reported: list[int] = []
        self.echo_user = False
        self.green_paths: list[str] = []
        self.status: Any = None


def _session_type(fake: _Fake) -> type:
    class FakeSession:
        run_timeout_s = 600
        context_window = 1
        llm_source = "fake"
        project_path = None
        read_only = False
        working_copy = None

        def __init__(self, **kwargs: Any) -> None:
            callbacks = kwargs["callbacks"]
            self.callbacks = callbacks
            self.on_step = kwargs.get("on_step", lambda _: None)
            fake.sessions += 1

            def status(value: str) -> None:
                event = ConversationStateUpdateEvent(key="execution_status", value=value)
                for callback in callbacks:
                    callback(event)

            fake.status = status

            def pause() -> None:
                fake.paused.set()
                if fake.confirm_pause:
                    event = ConversationStateUpdateEvent(key="execution_status", value="paused")
                    for callback in callbacks:
                        callback(event)

            def metrics() -> Any:
                if fake.fail_stats:
                    raise RuntimeError("stats down")
                return SimpleNamespace(
                    accumulated_token_usage=None, token_usages=[], accumulated_cost=0.0
                )

            self.workspace = SimpleNamespace(git_changes=lambda _path: [])
            self.conversation = SimpleNamespace(
                id="fake",
                state=SimpleNamespace(
                    events=[], refresh_from_server=lambda: {"execution_status": "running"}
                ),
                conversation_stats=SimpleNamespace(get_combined_metrics=metrics),
                pause=pause,
                reject_pending_actions=lambda: None,
                condense=lambda: fake.calls.append("condense"),
                send_message=fake.calls.append,
            )

        def final_text(self) -> str:
            return ""

        def fall_back_to_green(self) -> list[str]:
            return fake.green_paths

        def __enter__(self) -> Any:
            for step in fake.steps_reported:
                self.on_step(step)
            return self

        def __exit__(self, *_: object) -> None:
            fake.exited.set()

        def send(self, text: str, *, blocking: bool = True) -> None:
            if fake.fail_send is not None:
                raise fake.fail_send
            if fake.echo_user:
                echo = MessageEvent(
                    source="user",
                    llm_message=Message(role="user", content=[TextContent(text=text)]),
                )
                for callback in self.callbacks:
                    callback(echo)

    return FakeSession


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> _Fake:
    state = _Fake()
    monkeypatch.setattr(srv, "reap_orphan_sandboxes", lambda _keep=None: [])
    monkeypatch.setattr(
        srv,
        "load_openhands_config",
        lambda: SimpleNamespace(
            llm=SimpleNamespace(stream=False),
            sandbox=SimpleNamespace(persistent_conversations=False),
        ),
    )
    monkeypatch.setattr(srv, "build_mcp_config", lambda _selected, _config: ({}, []))
    monkeypatch.setattr(srv.memory, "recall_context", lambda _text: None)
    monkeypatch.setattr(srv.memory, "record_episode", lambda _draft, ended_at: None)
    monkeypatch.setattr(srv, "AgentSession", _session_type(state))
    monkeypatch.setattr(srv, "_CANCEL_GRACE_S", 0.1)
    return state


@pytest_asyncio.fixture
async def url(fake: _Fake) -> AsyncIterator[str]:
    async with serve(srv._handle_connection, "127.0.0.1", 0) as server:
        yield f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"


async def _start(ws: ClientConnection) -> None:
    await ws.send(json.dumps({"type": "start_session"}))
    await _until(ws, "session_started")


async def _until(ws: ClientConnection, wanted: str) -> dict[str, Any]:
    while True:
        message = json.loads(await asyncio.wait_for(ws.recv(), 10))
        if message["type"] == wanted:
            return message


async def _begin_turn(ws: ClientConnection) -> str:
    await ws.send(json.dumps({"type": "user_message", "text": "go"}))
    return (await _until(ws, "turn_started"))["turn_id"]


async def test_cancel_stops_the_agent_while_the_turn_runs(url: str, fake: _Fake) -> None:
    async with connect(url) as ws:
        await _start(ws)
        turn_id = await _begin_turn(ws)

        await ws.send(json.dumps({"type": "cancel_turn", "turn_id": turn_id}))
        finished = await _until(ws, "turn_finished")

    assert fake.paused.is_set()
    assert finished["reason"] == "cancelled"


async def test_cancel_ends_the_turn_even_if_the_agent_never_confirms(
    url: str, fake: _Fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.confirm_pause = False
    original = asyncio.wait_for

    async def fast_wait_for(awaitable: Any, timeout: float | None) -> Any:
        return await original(awaitable, 0.05 if timeout == 5.0 else timeout)

    monkeypatch.setattr(srv.asyncio, "wait_for", fast_wait_for)
    async with connect(url) as ws:
        await _start(ws)
        turn_id = await _begin_turn(ws)

        await ws.send(json.dumps({"type": "cancel_turn", "turn_id": turn_id}))
        finished = await _until(ws, "turn_finished")

    assert finished["reason"] == "cancelled"


async def test_second_message_during_a_turn_is_refused(url: str) -> None:
    async with connect(url) as ws:
        await _start(ws)
        await _begin_turn(ws)

        await ws.send(json.dumps({"type": "user_message", "text": "again"}))

        assert (await _until(ws, "error"))["code"] == "TURN_IN_PROGRESS"


async def test_disconnect_mid_turn_frees_the_session(url: str, fake: _Fake) -> None:
    async with connect(url) as ws:
        await _start(ws)
        await _begin_turn(ws)

    await asyncio.to_thread(fake.exited.wait, 5)
    assert fake.paused.is_set()

    async with connect(url) as ws:
        await _start(ws)
    assert fake.sessions == 2


async def test_a_failing_run_still_finishes_the_turn(url: str, fake: _Fake) -> None:
    fake.fail_send = RuntimeError("agent-server gone")
    async with connect(url) as ws:
        await _start(ws)
        await ws.send(json.dumps({"type": "user_message", "text": "go"}))

        assert (await _until(ws, "error"))["code"] == "TURN_FAILED"
        finished = await _until(ws, "turn_finished")

    assert finished["reason"] == "error"


async def test_failing_stats_do_not_lose_turn_finished(url: str, fake: _Fake) -> None:
    fake.fail_stats = True
    async with connect(url) as ws:
        await _start(ws)
        turn_id = await _begin_turn(ws)
        await ws.send(json.dumps({"type": "cancel_turn", "turn_id": turn_id}))

        assert (await _until(ws, "turn_finished"))["reason"] == "cancelled"


async def test_a_session_that_fails_to_start_leaves_the_bridge_usable(
    url: str, fake: _Fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Broken:
        def __init__(self, **_: Any) -> None:
            pass

        def __enter__(self) -> None:
            raise RuntimeError("Failed to run docker container")

    healthy = srv.AgentSession
    monkeypatch.setattr(srv, "AgentSession", Broken)
    async with connect(url) as ws:
        await ws.send(json.dumps({"type": "start_session"}))
        assert (await _until(ws, "error"))["code"] == "SESSION_START_FAILED"

        monkeypatch.setattr(srv, "AgentSession", healthy)
        await _start(ws)


async def test_interrupt_reaches_the_agent_during_the_turn(url: str, fake: _Fake) -> None:
    async with connect(url) as ws:
        await _start(ws)
        turn_id = await _begin_turn(ws)
        await ws.send(json.dumps({"type": "interrupt", "turn_id": turn_id, "text": "use tabs"}))
        await ws.send(json.dumps({"type": "cancel_turn", "turn_id": turn_id}))
        await _until(ws, "turn_finished")

    assert fake.calls == ["use tabs"]


async def test_compact_condenses_between_turns_only(url: str, fake: _Fake) -> None:
    async with connect(url) as ws:
        await _start(ws)
        await ws.send(json.dumps({"type": "compact"}))
        await _until(ws, "history_compacted")

        await _begin_turn(ws)
        await ws.send(json.dumps({"type": "compact"}))
        assert (await _until(ws, "error"))["code"] == "TURN_IN_PROGRESS"

    assert fake.calls == ["condense"]


def test_task_tracker_results_become_todo_items() -> None:
    task = SimpleNamespace(title="write tests", status="in_progress")
    event = SimpleNamespace(tool_name="task_tracker", observation=SimpleNamespace(task_list=[task]))

    items = srv._todo_items(event)  # type: ignore[arg-type]

    assert items is not None
    assert (items[0].text, items[0].state) == ("write tests", "active")
    assert srv._todo_items(SimpleNamespace(tool_name="terminal")) is None  # type: ignore[arg-type]


async def test_session_start_reports_each_step_before_session_started(
    url: str, fake: _Fake
) -> None:
    fake.steps_reported = [1, 2]
    async with connect(url) as ws:
        await ws.send(json.dumps({"type": "start_session"}))
        seen = [await _until(ws, "session_progress") for _ in range(3)]

    assert [m["current"] for m in seen] == [0, 1, 2]
    assert seen[0]["steps"] == list(STARTUP_STEPS)


async def test_user_echo_carries_what_was_written_not_the_prompt(
    url: str, fake: _Fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.echo_user = True
    monkeypatch.setattr(srv.memory, "recall_context", lambda _text: "<past_experience>x")
    block = {"kind": "instructions", "label": "instructions (CLAUDE.md)", "body": "LONG"}
    async with connect(url) as ws:
        await _start(ws)
        await ws.send(json.dumps({"type": "user_message", "text": "go", "context": [block]}))
        echo = await _until(ws, "event")

    assert "LONG" in echo["event"]["llm_message"]["content"][0]["text"]
    assert echo["user_display"] == {
        "text": "go",
        "loaded": ["instructions (CLAUDE.md)", "past lessons"],
    }


async def test_a_plain_message_has_no_user_display(url: str, fake: _Fake) -> None:
    fake.echo_user = True
    async with connect(url) as ws:
        await _start(ws)
        await _begin_turn(ws)
        assert (await _until(ws, "event"))["user_display"] is None


def _relay() -> tuple[srv._EventRelay, list[Any]]:
    sent: list[Any] = []
    conn = SimpleNamespace(
        turn_id="t1", send_threadsafe=sent.append, note_status_threadsafe=lambda _value: None
    )
    relay = srv._EventRelay(conn)  # type: ignore[arg-type]
    relay._buffering = False
    return relay, sent


def _agent_message(text: str) -> MessageEvent:
    return MessageEvent(
        source="agent", llm_message=Message(role="assistant", content=[TextContent(text=text)])
    )


def test_a_message_names_the_deltas_it_ends_and_the_next_one_starts_afresh() -> None:
    relay, sent = _relay()

    relay.on_event(StreamingDeltaEvent(content="he"))
    relay.on_event(StreamingDeltaEvent(content="llo"))
    relay.on_event(_agent_message("hello"))
    relay.on_event(StreamingDeltaEvent(content="next"))

    first, second, final, third = sent
    assert first.event_id == second.event_id == final.stream_id
    assert third.event_id != first.event_id


def test_a_message_that_was_not_streamed_has_no_stream_id() -> None:
    relay, sent = _relay()

    relay.on_event(_agent_message("hello"))

    assert sent[0].stream_id is None


async def test_the_iteration_cap_is_reported_with_what_was_set_aside(
    url: str, fake: _Fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.green_paths = ["a.cpp"]
    async with connect(url) as ws:
        await _start(ws)
        await _begin_turn(ws)
        await asyncio.to_thread(fake.status, "error")

        error = await _until(ws, "error")
        finished = await _until(ws, "turn_finished")

    assert error["code"] == "ITERATION_LIMIT"
    assert error["details"]["paths"] == ["a.cpp"]
    assert finished["reason"] == "error"
