"""Flat MCP-arg <-> agentmem DTO mapping (M2 boundary, mirrors kbase_mcp/mapping.py).
Kept separate from `tools/dispatch.py`: it only reshapes flat MCP args/results, it
never talks to the database itself."""

from __future__ import annotations

from typing import Any, Literal

from agentmem.schemas import Artifact, Episode, EpisodeAction, EpisodeSummary


def build_episode(
    *,
    episode_id: str,
    task_id: str,
    agent_profile: str,
    goal: str,
    started_at: str,
    ended_at: str,
    status: Literal["success", "failure", "partial", "abandoned"],
    summary: str,
    lessons: list[str],
    outcome: dict[str, Any] | None,
    actions: list[dict[str, Any]] | None,
    artifacts: list[dict[str, Any]] | None,
    tags: list[str] | None,
    branch: str | None,
    last_commit: str | None,
) -> Episode:
    """Maps flat `mem.remember` tool args to an `Episode` (pydantic validates the
    nested `actions`/`artifacts` dicts and parses the ISO timestamps)."""
    return Episode(
        episode_id=episode_id,
        task_id=task_id,
        agent_profile=agent_profile,
        goal=goal,
        started_at=started_at,
        ended_at=ended_at,
        status=status,
        summary=summary,
        lessons=lessons,
        outcome=outcome or {},
        actions=[EpisodeAction.model_validate(a) for a in (actions or [])],
        artifacts=[Artifact.model_validate(a) for a in (artifacts or [])],
        tags=tags or [],
        branch=branch,
        last_commit=last_commit,
    )


def episode_summaries_to_payload(summaries: list[EpisodeSummary]) -> dict[str, Any]:
    """`data` for `mem.recall`'s response envelope (WP07 §4)."""
    return {"episodes": [s.model_dump(mode="json") for s in summaries]}
