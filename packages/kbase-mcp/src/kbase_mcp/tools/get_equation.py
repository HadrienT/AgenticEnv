from __future__ import annotations

from typing import Annotated, Any

from corelib.db import session_scope
from kbase.lookup import get_equation as run_get_equation
from pydantic import Field

from kbase_mcp.tools.dispatch import call_args, dispatch


def get_equation(
    doc_key: Annotated[
        str | None, Field(description="The document's key; goes with equation_number.")
    ] = None,
    equation_number: Annotated[
        str | None,
        Field(description="The equation's number as the document prints it, e.g. '4.12'."),
    ] = None,
    chunk_id: Annotated[
        str | None, Field(description="Or the chunk_id of a search result holding the equation.")
    ] = None,
) -> dict[str, Any]:
    """One equation, its context and its citation. Give either `chunk_id` alone, or
    `doc_key` + `equation_number` together."""

    args = call_args(locals())

    def _run(timeout_s: int) -> tuple[dict[str, Any], dict[str, Any]]:
        with session_scope() as session:
            detail = run_get_equation(
                session, doc_key=doc_key, equation_number=equation_number, chunk_id=chunk_id
            )
        return detail.model_dump(mode="json"), {}

    return dispatch("kb.get_equation", _run, args=args)
