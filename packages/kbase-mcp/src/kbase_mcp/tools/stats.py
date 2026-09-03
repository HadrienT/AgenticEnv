from __future__ import annotations

from typing import Any

from corelib.db import session_scope
from kbase.ingestion.ops import stats as run_stats

from kbase_mcp.tools.dispatch import dispatch


def stats() -> dict[str, Any]:
    """Corpus counters (documents, chunks, equations, tables) and last ingestion date."""

    def _run(timeout_s: int) -> tuple[dict[str, Any], dict[str, Any]]:
        with session_scope() as session:
            report = run_stats(session)
        return report.model_dump(mode="json"), {}

    return dispatch("kb.stats", _run)
