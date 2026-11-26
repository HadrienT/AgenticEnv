from __future__ import annotations

from typing import Annotated, Any, Literal

from corelib.config import get_settings
from corelib.db import session_scope
from kbase.lookup import list_documents as run_list_documents
from kbase.schemas import Collection, Jurisdiction
from pydantic import Field

from kbase_mcp.tools.dispatch import call_args, dispatch


def list_documents(
    collection: Annotated[Collection, Field(description="The collection to list.")],
    jurisdiction: Annotated[
        Jurisdiction | None, Field(description="Regulation only: documents of this jurisdiction.")
    ] = None,
    topic: Annotated[
        str | None, Field(description="Only this topic, as kb.list_topics names it.")
    ] = None,
    doc_type: Annotated[
        Literal["standard", "law", "guidance", "proposal"] | None,
        Field(description="Regulation only: binding law, guidance, a standard or a proposal."),
    ] = None,
) -> dict[str, Any]:
    """Documents of a collection with doc_key, title, doc_type, topic, jurisdiction and
    validity (WP21 §3). Example: `list_documents(collection="regulation",
    jurisdiction="eu", topic="reg-ccr-sa-ccr")`."""

    args = call_args(locals())

    def _run(timeout_s: int) -> tuple[dict[str, Any], dict[str, Any]]:
        get_settings()
        with session_scope() as session:
            listing = run_list_documents(
                session,
                collection=collection,
                jurisdiction=jurisdiction,
                topic=topic,
                doc_type=doc_type,
            )
        return listing.model_dump(mode="json"), {}

    return dispatch("kb.list_documents", _run, args=args)
