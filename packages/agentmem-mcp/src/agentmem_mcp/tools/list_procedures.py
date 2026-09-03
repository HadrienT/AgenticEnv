from __future__ import annotations

from typing import Any

from agentmem.procedural import list_procedures as run_list_procedures

from agentmem_mcp.tools.dispatch import dispatch


def list_procedures(tags: list[str] | None = None) -> dict[str, Any]:
    """List available reusable procedures (recipes), optionally filtered by tags.
    Read-only cache of `agents/procedures/*.yaml`.
    Example: `list_procedures(tags=["calibration"])`."""

    def _run(timeout_s: int) -> tuple[dict[str, Any], dict[str, Any]]:
        summaries = run_list_procedures(tags=tags)
        return {"procedures": [s.model_dump(mode="json") for s in summaries]}, {}

    return dispatch("mem.list_procedures", _run)
