from __future__ import annotations

import logging

import pytest
from corelib.db import apply_migrations
from corelib.obs import ToolInvocation, record_tool_invocation
from corelib.time import utc_now

pytestmark = pytest.mark.integration


def _make_invocation(**overrides: object) -> ToolInvocation:
    base: dict[str, object] = {
        "id": "test-obs-id",
        "ts": utc_now(),
        "server": "kbase",
        "tool": "kb.search",
        "args": {"query": "SABR"},
        "status": "ok",
        "duration_ms": 12,
    }
    base.update(overrides)
    return ToolInvocation.model_validate(base)


def test_record_tool_invocation_persists_row() -> None:
    apply_migrations()
    record_tool_invocation(_make_invocation(id="test-obs-persist"))


def test_record_tool_invocation_never_raises_when_db_unreachable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _boom() -> None:
        raise RuntimeError("connection refused")

    monkeypatch.setattr("corelib.obs.session_scope", lambda: _boom())

    with caplog.at_level(logging.WARNING, logger="corelib.obs"):
        record_tool_invocation(_make_invocation(id="test-obs-down"))

    assert any("failed to persist tool invocation" in r.message for r in caplog.records)
