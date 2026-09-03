"""`dedup`: idempotence via `kb.document_versions.sha256` (WP04 §8)."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session


def already_ingested(session: Session, sha256: str) -> uuid.UUID | None:
    """Returns the existing `document_versions.id` for this content hash, if any."""
    row = session.execute(
        text("SELECT id FROM kb.document_versions WHERE sha256 = :sha256"),
        {"sha256": sha256},
    ).first()
    return row[0] if row else None
