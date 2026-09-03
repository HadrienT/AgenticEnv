from __future__ import annotations

from typing import Any

from agentmem.config import load_agentmem_config
from agentmem.embeddings import HashingEmbedder
from agentmem.episodic import recall as run_recall

from agentmem_mcp.mapping import episode_summaries_to_payload
from agentmem_mcp.tools.dispatch import dispatch


def recall(
    query: str,
    k: int | None = None,
    tags: list[str] | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Find similar past episodes (goal/summary/lessons) before starting a task, so you
    don't repeat a known mistake. Returns summaries only, never the full action trace.
    Example: `recall(query="calibrate Heston on a vol surface", k=5)`."""

    def _run(timeout_s: int) -> tuple[dict[str, Any], dict[str, Any]]:
        config = load_agentmem_config()
        embedder = HashingEmbedder(dim=config.embeddings.dim, normalize=config.embeddings.normalize)
        episodes = run_recall(
            query,
            k=k if k is not None else config.episodic.recall_default_k,
            tags=tags,
            status=status,
            embedder=embedder,
            min_similarity=config.episodic.min_similarity,
        )
        return episode_summaries_to_payload(episodes), {}

    return dispatch("mem.recall", _run)
