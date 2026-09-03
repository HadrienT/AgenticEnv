from __future__ import annotations

import pytest
from agentmem.embeddings import HashingEmbedder
from agentmem.episodic import get_episode, recall, remember
from agentmem.schemas import Episode, EpisodeAction
from corelib.errors import NotFoundError, ValidationError
from corelib.ids import new_id
from corelib.time import utc_now

pytestmark = pytest.mark.integration

_DIM = 256


def _episode(**overrides: object) -> Episode:
    now = utc_now()
    defaults: dict[str, object] = {
        "episode_id": new_id(),
        "task_id": "task-1",
        "agent_profile": "quant",
        "goal": "calibrate a Heston model on a vol surface",
        "started_at": now,
        "ended_at": now,
        "status": "success",
        "summary": "Calibrated Heston via differential evolution then an L-BFGS polish.",
        "lessons": ["use parameter bounds and multiple initializations for stability"],
        "tags": ["calibration", "heston"],
    }
    defaults.update(overrides)
    return Episode.model_validate(defaults)


def test_remember_then_recall_finds_the_episode(clean_mem_tables: None) -> None:
    embedder = HashingEmbedder(dim=_DIM)
    episode = _episode()
    remember(episode, embedder=embedder)

    results = recall(
        "calibrate a Heston model on a vol surface",
        k=5,
        embedder=embedder,
        min_similarity=0.0,
    )
    assert any(r.episode_id == episode.episode_id for r in results)


def test_recall_summary_schema_has_no_actions_field() -> None:
    from agentmem.schemas import EpisodeSummary

    assert "actions" not in EpisodeSummary.model_fields


def test_recall_filters_by_tags(clean_mem_tables: None) -> None:
    embedder = HashingEmbedder(dim=_DIM)
    heston = _episode(tags=["calibration", "heston"])
    ingestion = _episode(goal="ingest a new document into the knowledge base", tags=["ingestion"])
    remember(heston, embedder=embedder)
    remember(ingestion, embedder=embedder)

    results = recall(
        "calibrate a Heston model", k=5, tags=["heston"], embedder=embedder, min_similarity=0.0
    )
    ids = {r.episode_id for r in results}
    assert heston.episode_id in ids
    assert ingestion.episode_id not in ids


def test_recall_filters_by_status(clean_mem_tables: None) -> None:
    embedder = HashingEmbedder(dim=_DIM)
    ok = _episode(status="success")
    failed = _episode(status="failure")
    remember(ok, embedder=embedder)
    remember(failed, embedder=embedder)

    results = recall(
        "calibrate a Heston model", k=5, status="failure", embedder=embedder, min_similarity=0.0
    )
    ids = {r.episode_id for r in results}
    assert failed.episode_id in ids
    assert ok.episode_id not in ids


def test_recall_min_similarity_gates_off_topic_queries(clean_mem_tables: None) -> None:
    embedder = HashingEmbedder(dim=_DIM)
    episode = _episode()
    remember(episode, embedder=embedder)

    results = recall(
        "completely unrelated query about penguins and ice cream",
        k=5,
        embedder=embedder,
        min_similarity=0.99,
    )
    assert results == []


def test_remember_rejects_empty_summary() -> None:
    embedder = HashingEmbedder(dim=_DIM)
    episode = _episode(summary="   ")
    with pytest.raises(ValidationError):
        remember(episode, embedder=embedder)


def test_remember_rejects_empty_lessons() -> None:
    embedder = HashingEmbedder(dim=_DIM)
    episode = _episode(lessons=[])
    with pytest.raises(ValidationError):
        remember(episode, embedder=embedder)


def test_remember_rejects_a_secret_pattern() -> None:
    embedder = HashingEmbedder(dim=_DIM)
    episode = _episode(summary="used api_key=sk-abcdefghijklmnopqrstuvwx to call the pricing api")
    with pytest.raises(ValidationError):
        remember(episode, embedder=embedder)


def test_remember_rejects_a_host_path() -> None:
    embedder = HashingEmbedder(dim=_DIM)
    episode = _episode(goal="fix a bug in /home/alice/project/file.py")
    with pytest.raises(ValidationError):
        remember(episode, embedder=embedder)


def test_get_episode_returns_the_full_trace(clean_mem_tables: None) -> None:
    embedder = HashingEmbedder(dim=_DIM)
    episode = _episode(
        actions=[
            EpisodeAction(
                ordinal=0,
                kind="tool",
                name="quant.calibrate",
                args={"model": "heston"},
                result_summary="rmse=0.01",
                status="ok",
                duration_ms=1200,
            )
        ],
    )
    remember(episode, embedder=embedder)

    fetched = get_episode(episode.episode_id)
    assert fetched.actions[0].name == "quant.calibrate"


def test_get_episode_unknown_raises_not_found(clean_mem_tables: None) -> None:
    with pytest.raises(NotFoundError):
        get_episode("does-not-exist")


def test_episode_is_immutable(clean_mem_tables: None) -> None:
    from corelib.db import session_scope
    from sqlalchemy import text

    embedder = HashingEmbedder(dim=_DIM)
    episode = _episode()
    remember(episode, embedder=embedder)

    with pytest.raises(Exception, match="immutable"), session_scope() as session:
        session.execute(
            text("UPDATE mem.episodes SET summary = 'changed' WHERE episode_id = :id"),
            {"id": episode.episode_id},
        )
