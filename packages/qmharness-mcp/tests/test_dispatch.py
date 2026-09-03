from __future__ import annotations

import pytest
from corelib.errors import PermissionDeniedError
from mcp.server.mcpserver.exceptions import ToolError
from qmharness_mcp.schemas import McpServerConfig
from qmharness_mcp.tools import dispatch as dispatch_mod
from qmharness_mcp.tools.dispatch import dispatch


def _config(**overrides: object) -> McpServerConfig:
    defaults: dict[str, object] = {
        "name": "qmharness",
        "tools_allowlist": ["qm.run"],
        "default_timeout_s": 30,
    }
    defaults.update(overrides)
    return McpServerConfig.model_validate(defaults)


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dispatch_mod, "record_tool_invocation", lambda inv: None)


def test_dispatch_returns_an_ok_envelope_on_success() -> None:
    dispatch_mod.init(_config())
    result = dispatch("qm.run", lambda timeout_s: {"ok": True, "timeout_s": timeout_s})
    assert result == {
        "ok": True,
        "data": {"ok": True, "timeout_s": 30},
        "meta": {"truncated": False},
    }


def test_dispatch_rejects_a_tool_outside_the_allowlist() -> None:
    dispatch_mod.init(_config(tools_allowlist=["qm.compare"]))
    with pytest.raises(PermissionDeniedError):
        dispatch("qm.run", lambda timeout_s: {})


def test_dispatch_maps_an_app_error_to_a_tool_error_the_model_can_read() -> None:
    from corelib.errors import DependencyError

    dispatch_mod.init(_config())

    def _boom(timeout_s: int) -> dict[str, object]:
        raise DependencyError("module not importable", details={})

    with pytest.raises(ToolError, match="module not importable"):
        dispatch("qm.run", _boom)


def test_dispatch_lets_unexpected_exceptions_propagate_for_the_sdk_to_handle() -> None:
    dispatch_mod.init(_config())

    def _boom(timeout_s: int) -> dict[str, object]:
        raise KeyError("unexpected")

    with pytest.raises(KeyError):
        dispatch("qm.run", _boom)


def test_dispatch_truncates_an_oversized_result() -> None:
    dispatch_mod.init(_config(max_result_bytes=32))
    result = dispatch("qm.run", lambda timeout_s: {"blob": "x" * 1_000})
    assert result["meta"]["truncated"] is True
