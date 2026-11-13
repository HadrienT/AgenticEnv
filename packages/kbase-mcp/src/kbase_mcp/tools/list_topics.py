from __future__ import annotations

from typing import Any

from corelib.config import get_settings
from corelib.db import session_scope
from kbase.config import load_kbase_config
from kbase.lookup import list_topics as run_list_topics

from kbase_mcp.tools.dispatch import dispatch


def list_topics() -> dict[str, Any]:
    """Collections of the base with their description, topics (document counts), doc
    types and year range — call before searching blindly, to know which collection and
    filters are worth using."""

    def _run(timeout_s: int) -> tuple[dict[str, Any], dict[str, Any]]:
        get_settings()
        config = load_kbase_config()
        descriptions = {name: c.description for name, c in config.collections.items()}
        jurisdictions = {name: c.description for name, c in config.jurisdictions.items()}
        with session_scope() as session:
            summary = run_list_topics(
                session, descriptions=descriptions, jurisdiction_descriptions=jurisdictions
            )
        return summary.model_dump(mode="json"), {}

    return dispatch("kb.list_topics", _run)
