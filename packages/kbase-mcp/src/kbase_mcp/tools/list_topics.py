from __future__ import annotations

from typing import Any

from corelib.db import session_scope
from kbase.lookup import list_topics as run_list_topics

from kbase_mcp.tools.dispatch import dispatch


def list_topics() -> dict[str, Any]:
    """Topics, asset classes and year range covered by the base — call before searching
    blindly, to know what filters are worth using."""

    def _run(timeout_s: int) -> tuple[dict[str, Any], dict[str, Any]]:
        with session_scope() as session:
            summary = run_list_topics(session)
        return summary.model_dump(mode="json"), {}

    return dispatch("kb.list_topics", _run)
