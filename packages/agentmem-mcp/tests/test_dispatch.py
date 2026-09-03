from __future__ import annotations

import pytest
from agentmem_mcp.schemas import McpServerConfig
from agentmem_mcp.tools import dispatch as dispatch_mod
from agentmem_mcp.tools.dispatch import dispatch
from corelib.errors import PermissionDeniedError
from mcp.server.mcpserver.exceptions import ToolError


def _config(**overrides: object) -> McpServerConfig:
    defaults: dict[str, object] = {
        "name": "agentmem",
        "tools_allowlist": ["mem.recall"],
        "default_timeout_s": 30,
    }
    defaults.update(overrides)
    return McpServerConfig.model_validate(defaults)


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dispatch_mod, "record_tool_invocation", lambda inv: None)


def test_dispatch_returns_an_ok_envelope_on_success() -> None:
    dispatch_mod.init(_config())
    result = dispatch("mem.recall", lambda timeout_s: ({"episodes": []}, {}))
    assert result == {"ok": True, "data": {"episodes": []}, "meta": {"truncated": False}}


def test_dispatch_merges_meta_extra_into_the_envelope_meta() -> None:
    dispatch_mod.init(_config())
    result = dispatch("mem.recall", lambda timeout_s: ({"episodes": []}, {"foo": "bar"}))
    assert result["meta"] == {"truncated": False, "foo": "bar"}


def test_dispatch_rejects_a_tool_outside_the_allowlist() -> None:
    dispatch_mod.init(_config(tools_allowlist=["mem.remember"]))
    with pytest.raises(PermissionDeniedError):
        dispatch("mem.recall", lambda timeout_s: ({}, {}))


def test_dispatch_maps_an_app_error_to_a_tool_error_the_model_can_read() -> None:
    from corelib.errors import ValidationError

    dispatch_mod.init(_config(tools_allowlist=["mem.remember"]))

    def _boom(timeout_s: int) -> tuple[dict[str, object], dict[str, object]]:
        raise ValidationError("mem.remember requires confirm=true", details={})

    with pytest.raises(ToolError, match="confirm=true"):
        dispatch("mem.remember", _boom)


def test_dispatch_lets_unexpected_exceptions_propagate_for_the_sdk_to_handle() -> None:
    dispatch_mod.init(_config())

    def _boom(timeout_s: int) -> tuple[dict[str, object], dict[str, object]]:
        raise KeyError("unexpected")

    with pytest.raises(KeyError):
        dispatch("mem.recall", _boom)


def test_dispatch_truncates_an_oversized_result() -> None:
    dispatch_mod.init(_config(max_result_bytes=32))
    result = dispatch("mem.recall", lambda timeout_s: ({"blob": "x" * 1_000}, {}))
    assert result["meta"]["truncated"] is True
