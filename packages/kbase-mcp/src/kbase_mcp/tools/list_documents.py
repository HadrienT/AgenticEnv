from __future__ import annotations

from typing import Any, Literal

from corelib.config import get_settings
from corelib.db import session_scope
from kbase.lookup import list_documents as run_list_documents
from kbase.schemas import Collection, Jurisdiction

from kbase_mcp.tools.dispatch import dispatch


def list_documents(
    collection: Collection,
    jurisdiction: Jurisdiction | None = None,
    topic: str | None = None,
    doc_type: Literal["standard", "law", "guidance", "proposal"] | None = None,
) -> dict[str, Any]:
    """Documents of a collection with doc_key, title, doc_type, topic, jurisdiction and
    validity (WP21 §3). Example: `list_documents(collection="regulation",
    jurisdiction="eu", topic="reg-ccr-sa-ccr")`."""

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

    return dispatch("kb.list_documents", _run)
