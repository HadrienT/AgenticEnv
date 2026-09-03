from __future__ import annotations

import pytest
from corelib.db import apply_migrations, session_scope
from sqlalchemy import text


@pytest.fixture
def clean_mem_tables() -> None:
    """Truncates all `mem.*` tables so integration tests get a clean slate. Episodes
    are immutable and PK-unique, but `recall`'s vector search can otherwise pick up
    residue from earlier runs on a shared dev database (WP05's noted DB-pollution
    gotcha applies here too)."""
    apply_migrations()
    with session_scope() as session:
        session.execute(
            text("TRUNCATE mem.episode_actions, mem.artifacts, mem.episodes, mem.procedures")
        )
