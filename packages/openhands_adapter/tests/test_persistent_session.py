"""WP08e: one sandbox, several conversations, each with its own copy. No Docker."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands_adapter.session import AgentSession, _persisted_volumes

from openhands_adapter import session as module


class _Action:
    pass


def _join_threads() -> None:
    for thread in threading.enumerate():
        if thread is not threading.current_thread() and thread.daemon:
            thread.join(timeout=1)


class _Copy:
    created: list[str]

    def __init__(self, _workspace: object, root: str) -> None:
        self.root = root
        _Copy.created.append(root)

    def initialize(self) -> None:
        pass

    is_git = True


def _session(monkeypatch: pytest.MonkeyPatch, *, persistent: bool) -> tuple[AgentSession, list]:
    calls: list[dict[str, Any]] = []

    class FakeRemote:
        def __init__(self, conversation_id: uuid.UUID | None) -> None:
            self.id = conversation_id or uuid.uuid4()

        def set_confirmation_policy(self, _policy: object) -> None:
            pass

    def conversation(_agent: object, **kwargs: Any) -> FakeRemote:
        calls.append({**kwargs, "working_dir": kwargs["workspace"].working_dir})
        return FakeRemote(kwargs["conversation_id"])

    _Copy.created = []
    monkeypatch.setattr(module, "Conversation", conversation)
    monkeypatch.setattr(module, "RemoteConversation", FakeRemote)
    monkeypatch.setattr(module, "WorkingCopy", _Copy)
    monkeypatch.setattr(module, "_ensure_llm", lambda *_: "create_payload")
    session = AgentSession(
        oh_config=SimpleNamespace(
            llm=SimpleNamespace(sandbox_base_url="x"),
            run=SimpleNamespace(max_iterations=1),
            sandbox=SimpleNamespace(image="image"),
        ),  # type: ignore[arg-type]
        project_path="/tmp",
        persistent=persistent,
    )
    session._agent = object()  # type: ignore[assignment]
    session._workspace = SimpleNamespace(working_dir="/workspace/project")  # type: ignore[assignment]
    return session, calls


def test_each_conversation_gets_its_own_copy_and_survives_the_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, calls = _session(monkeypatch, persistent=True)

    first = session.open_conversation()
    second = session.open_conversation()

    assert _Copy.created == [f"/workspace/project/{first}", f"/workspace/project/{second}"]
    assert calls[1]["working_dir"] == f"/workspace/project/{second}"
    assert not calls[0]["delete_on_close"]


def test_going_back_keeps_the_copy_and_makes_no_new_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, calls = _session(monkeypatch, persistent=True)
    first = session.open_conversation()
    copy = session.working_copy
    session.open_conversation()

    assert session.open_conversation(first) == first
    assert session.working_copy is copy
    assert len(calls) == 2


def test_a_stored_conversation_is_asked_for_by_its_id(monkeypatch: pytest.MonkeyPatch) -> None:
    session, calls = _session(monkeypatch, persistent=True)
    stored = str(uuid.uuid4())

    assert session.open_conversation(stored) == stored
    assert calls[0]["conversation_id"] == uuid.UUID(stored)


def test_a_plain_session_stays_as_it_was(monkeypatch: pytest.MonkeyPatch) -> None:
    session, calls = _session(monkeypatch, persistent=False)

    session.open_conversation()

    assert _Copy.created == ["/workspace/project"]
    assert calls[0]["conversation_id"] is None
    assert calls[0]["delete_on_close"]


def test_persisted_folders_are_writable_by_the_sandbox_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(module, "persistence_dir", lambda: tmp_path)

    volumes = _persisted_volumes()

    assert volumes == [
        f"{tmp_path}/conversations:/workspace/conversations",
        f"{tmp_path}/bash_events:/workspace/bash_events",
    ]
    assert (tmp_path / "conversations").stat().st_mode & 0o777 == 0o777


def _cap_session(monkeypatch: pytest.MonkeyPatch, *, events: list[object]) -> AgentSession:
    session, _ = _session(monkeypatch, persistent=False)
    session._conversation = SimpleNamespace(state=SimpleNamespace(events=events))  # type: ignore[assignment]
    session._working_copy = SimpleNamespace(restore_green=lambda: ["a.cpp"])  # type: ignore[assignment]
    return session


def test_the_cap_sends_the_copy_back_to_the_last_build(monkeypatch: pytest.MonkeyPatch) -> None:
    capped = ConversationErrorEvent(source="environment", code="MaxIterationsReached", detail="x")

    assert _cap_session(monkeypatch, events=[capped]).fall_back_to_green() == ["a.cpp"]


def test_another_error_leaves_the_copy_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    other = ConversationErrorEvent(source="environment", code="ExecutionError", detail="x")

    assert _cap_session(monkeypatch, events=[other]).fall_back_to_green() == []


def test_the_agent_is_warned_once_before_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    session, _ = _session(monkeypatch, persistent=False)
    warned: list[str] = []
    monkeypatch.setattr(session, "_warn_of_the_cap", lambda: warned.append("warned"))
    monkeypatch.setattr(module, "ActionEvent", _Action)
    monkeypatch.setattr(AgentSession, "_max_iterations", 20)

    for _ in range(19):
        session._watch_iterations(_Action())  # type: ignore[arg-type]

    _join_threads()
    assert warned == ["warned"]
