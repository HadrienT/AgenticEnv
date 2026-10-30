"""WP14 §2: a session leaves an episode behind, and the next one gets it back."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from agentmem.embeddings import HashingEmbedder
from corelib.db import apply_migrations, session_scope
from openhands_bridge import memory
from sqlalchemy import text


def _draft() -> memory.SessionDraft:
    return memory.SessionDraft(
        conversation_id="c1",
        profile="coding",
        started_at=datetime.now(UTC),
        project="quant-modeling",
        messages=["add a barrier pricer"],
        changed_files=["src/pricers/registry.cpp"],
    )


_ANSWER = json.dumps(
    {
        "summary": "Added a barrier pricer and registered it.",
        "lessons": ["Register new pricers in registry.cpp under register_pricer."],
        "tags": ["pricer"],
    }
)


def test_parse_summary_accepts_json_inside_prose() -> None:
    assert memory.parse_summary(f"Here it is:\n```json\n{_ANSWER}\n```") is not None


@pytest.mark.parametrize("answer", ["no json", "{broken", '{"summary": "x"}', '{"lessons": ["l"]}'])
def test_parse_summary_refuses_what_it_cannot_use(answer: str) -> None:
    assert memory.parse_summary(answer) is None


def test_an_empty_session_records_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_prompt: str) -> str:
        raise AssertionError("the LLM must not be called")

    monkeypatch.setattr(memory, "_ask_llm", fail)
    draft = _draft()
    draft.messages = []

    assert memory.record_episode(draft, ended_at=datetime.now(UTC)) is None


def test_an_unreachable_llm_loses_the_episode_not_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_prompt: str) -> str:
        raise OSError("connection refused")

    monkeypatch.setattr(memory, "_ask_llm", fail)

    assert memory.record_episode(_draft(), ended_at=datetime.now(UTC)) is None


@pytest.mark.integration
def test_a_session_is_recalled_by_the_next_one(monkeypatch: pytest.MonkeyPatch) -> None:
    apply_migrations()
    with session_scope() as session:
        session.execute(text("TRUNCATE mem.episode_actions, mem.artifacts, mem.episodes"))
    monkeypatch.setattr(memory, "_ask_llm", lambda _prompt: _ANSWER)
    monkeypatch.setattr(memory, "build_embedder", lambda _config: HashingEmbedder(dim=1024))

    episode_id = memory.record_episode(_draft(), ended_at=datetime.now(UTC))
    context = memory.recall_context("add a barrier pricer to the registry")

    assert episode_id is not None
    assert context is not None
    assert "register_pricer" in context


@pytest.mark.integration
def test_a_secret_in_the_summary_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    apply_migrations()
    answer = json.dumps({"summary": "password=hunter2 worked", "lessons": ["keep it"]})
    monkeypatch.setattr(memory, "_ask_llm", lambda _prompt: answer)
    monkeypatch.setattr(memory, "build_embedder", lambda _config: HashingEmbedder(dim=1024))

    assert memory.record_episode(_draft(), ended_at=datetime.now(UTC)) is None
