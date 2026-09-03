from __future__ import annotations

from typing import Any

from corelib.db import session_scope
from kbase.lookup import get_document as run_get_document

from kbase_mcp.tools.dispatch import dispatch


def get_document(
    doc_key: str | None = None, document_version_id: str | None = None
) -> dict[str, Any]:
    """Metadata + section tree of one document. Give either `doc_key` (latest version)
    or `document_version_id` (a specific version), never both."""

    def _run(timeout_s: int) -> tuple[dict[str, Any], dict[str, Any]]:
        with session_scope() as session:
            detail = run_get_document(
                session, doc_key=doc_key, document_version_id=document_version_id
            )
        return detail.model_dump(mode="json"), {}

    return dispatch("kb.get_document", _run)
