from __future__ import annotations

from datetime import UTC, datetime

from agentmem.schemas import EpisodeSummary
from agentmem_mcp.mapping import build_episode, episode_summaries_to_payload


def test_build_episode_maps_flat_args_and_parses_nested_shapes() -> None:
    episode = build_episode(
        episode_id="e1",
        task_id="t1",
        agent_profile="quant",
        goal="calibrate SABR",
        started_at="2026-09-03T10:00:00Z",
        ended_at="2026-09-03T10:20:00Z",
        status="success",
        summary="done",
        lessons=["use bounds"],
        outcome={"rmse": 0.01},
        actions=[
            {
                "ordinal": 0,
                "kind": "tool",
                "name": "quant.calibrate",
                "args": {},
                "result_summary": "ok",
                "status": "ok",
                "duration_ms": 100,
            }
        ],
        artifacts=[{"kind": "log", "path": "run.log", "sha256": "abc"}],
        tags=["calibration"],
        branch="main",
        last_commit="deadbeef",
    )
    assert episode.episode_id == "e1"
    assert episode.started_at.year == 2026
    assert episode.actions[0].name == "quant.calibrate"
    assert episode.artifacts[0].path == "run.log"


def test_build_episode_defaults_optional_fields_to_empty() -> None:
    episode = build_episode(
        episode_id="e2",
        task_id="t2",
        agent_profile="quant",
        goal="g",
        started_at="2026-09-03T10:00:00Z",
        ended_at="2026-09-03T10:20:00Z",
        status="failure",
        summary="s",
        lessons=["l"],
        outcome=None,
        actions=None,
        artifacts=None,
        tags=None,
        branch=None,
        last_commit=None,
    )
    assert episode.outcome == {}
    assert episode.actions == []
    assert episode.artifacts == []
    assert episode.tags == []


def test_episode_summaries_to_payload_shapes_the_response() -> None:
    summary = EpisodeSummary(
        episode_id="e1",
        task_id="t1",
        agent_profile="quant",
        goal="g",
        started_at=datetime(2026, 9, 3, tzinfo=UTC),
        ended_at=datetime(2026, 9, 3, tzinfo=UTC),
        status="success",
        summary="s",
        outcome={},
        lessons=["l"],
        tags=[],
        branch=None,
        last_commit=None,
        similarity=0.9,
    )
    payload = episode_summaries_to_payload([summary])
    assert payload["episodes"][0]["episode_id"] == "e1"
    assert payload["episodes"][0]["similarity"] == 0.9
