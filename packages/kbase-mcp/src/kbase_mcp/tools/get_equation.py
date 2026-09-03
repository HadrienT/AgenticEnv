from __future__ import annotations

from typing import Any

from corelib.db import session_scope
from kbase.lookup import get_equation as run_get_equation

from kbase_mcp.tools.dispatch import dispatch


def get_equation(
    doc_key: str | None = None,
    equation_number: str | None = None,
    chunk_id: str | None = None,
) -> dict[str, Any]:
    """One equation, its context and its citation. Give either `chunk_id` alone, or
    `doc_key` + `equation_number` together."""

    def _run(timeout_s: int) -> tuple[dict[str, Any], dict[str, Any]]:
        with session_scope() as session:
            detail = run_get_equation(
                session, doc_key=doc_key, equation_number=equation_number, chunk_id=chunk_id
            )
        return detail.model_dump(mode="json"), {}

    return dispatch("kb.get_equation", _run)
