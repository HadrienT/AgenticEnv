from __future__ import annotations

from typing import Any, Literal

from agentmem.config import load_agentmem_config
from agentmem.embeddings import HashingEmbedder
from agentmem.episodic import remember as run_remember
from corelib.errors import ValidationError

from agentmem_mcp.mapping import build_episode
from agentmem_mcp.tools.dispatch import dispatch


def remember(
    episode_id: str,
    task_id: str,
    agent_profile: str,
    goal: str,
    started_at: str,
    ended_at: str,
    status: Literal["success", "failure", "partial", "abandoned"],
    summary: str,
    lessons: list[str],
    outcome: dict[str, Any] | None = None,
    actions: list[dict[str, Any]] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    tags: list[str] | None = None,
    branch: str | None = None,
    last_commit: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Persist one finished task as an immutable episode (SEC7: requires `confirm=true`).
    `summary` and `lessons` are mandatory and must be non-empty. `started_at`/`ended_at`
    are ISO-8601 timestamps. Example: `remember(episode_id="task-42", task_id="task-42",
    agent_profile="quant", goal="calibrate SABR", started_at="2026-09-03T10:00:00Z",
    ended_at="2026-09-03T10:20:00Z", status="success", summary="...", lessons=["..."],
    confirm=true)`."""

    def _run(timeout_s: int) -> tuple[dict[str, Any], dict[str, Any]]:
        if not confirm:
            raise ValidationError("mem.remember requires confirm=true", details={})
        episode = build_episode(
            episode_id=episode_id,
            task_id=task_id,
            agent_profile=agent_profile,
            goal=goal,
            started_at=started_at,
            ended_at=ended_at,
            status=status,
            summary=summary,
            lessons=lessons,
            outcome=outcome,
            actions=actions,
            artifacts=artifacts,
            tags=tags,
            branch=branch,
            last_commit=last_commit,
        )
        config = load_agentmem_config()
        embedder = HashingEmbedder(dim=config.embeddings.dim, normalize=config.embeddings.normalize)
        written_id = run_remember(
            episode, embedder=embedder, embed_summary=config.episodic.embed_summary
        )
        return {"episode_id": written_id}, {}

    return dispatch("mem.remember", _run)
