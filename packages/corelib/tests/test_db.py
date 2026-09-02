from __future__ import annotations

import uuid

import pytest
from corelib.db import apply_migrations, session_scope
from sqlalchemy import text

pytestmark = pytest.mark.integration


def test_apply_migrations_on_up_to_date_db_is_a_noop() -> None:
    apply_migrations()  # ensure applied at least once
    report = apply_migrations()
    assert report.already_up_to_date is True
    assert report.applied == []


def test_apply_migrations_creates_expected_schema() -> None:
    apply_migrations()
    with session_scope() as session:
        obs_schema = session.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = 'obs'")
        ).first()
        tool_invocations = session.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'obs' AND table_name = 'tool_invocations'"
            )
        ).first()
    assert obs_schema is not None
    assert tool_invocations is not None


def test_session_scope_rolls_back_on_exception() -> None:
    apply_migrations()
    marker = f"test-{uuid.uuid4()}"
    with pytest.raises(RuntimeError), session_scope() as session:
        session.execute(
            text(
                "INSERT INTO obs.tool_invocations "
                "(id, ts, server, tool, args, args_sha, status, duration_ms) "
                "VALUES (:id, now(), 's', 't', '{}'::jsonb, 'sha', 'ok', 1)"
            ),
            {"id": marker},
        )
        raise RuntimeError("boom")

    with session_scope() as session:
        row = session.execute(
            text("SELECT 1 FROM obs.tool_invocations WHERE id = :id"), {"id": marker}
        ).first()
    assert row is None


def test_session_scope_commits_on_normal_exit() -> None:
    apply_migrations()
    marker = f"test-{uuid.uuid4()}"
    with session_scope() as session:
        session.execute(
            text(
                "INSERT INTO obs.tool_invocations "
                "(id, ts, server, tool, args, args_sha, status, duration_ms) "
                "VALUES (:id, now(), 's', 't', '{}'::jsonb, 'sha', 'ok', 1)"
            ),
            {"id": marker},
        )

    with session_scope() as session:
        row = session.execute(
            text("SELECT 1 FROM obs.tool_invocations WHERE id = :id"), {"id": marker}
        ).first()
    assert row is not None
