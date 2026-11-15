from __future__ import annotations

import pytest
from corelib.errors import PermissionDeniedError
from kbase_mcp.schemas import McpServerConfig
from kbase_mcp.tools import dispatch as dispatch_mod
from kbase_mcp.tools.dispatch import dispatch
from mcp.server.mcpserver.exceptions import ToolError


def _config(**overrides: object) -> McpServerConfig:
    defaults: dict[str, object] = {
        "name": "kbase",
        "tools_allowlist": ["kb.search"],
        "default_timeout_s": 30,
    }
    defaults.update(overrides)
    return McpServerConfig.model_validate(defaults)


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dispatch_mod, "record_tool_invocation", lambda inv: None)


def test_dispatch_returns_an_ok_envelope_on_success() -> None:
    dispatch_mod.init(_config())
    result = dispatch("kb.search", lambda timeout_s: ({"ok": True, "timeout_s": timeout_s}, {}))
    assert result == {
        "ok": True,
        "data": {"ok": True, "timeout_s": 30},
        "meta": {"truncated": False},
    }


def test_dispatch_merges_meta_extra_into_the_envelope_meta() -> None:
    dispatch_mod.init(_config())
    result = dispatch("kb.search", lambda timeout_s: ({"results": []}, {"strategy_used": "hybrid"}))
    assert result["meta"] == {"truncated": False, "strategy_used": "hybrid"}


def test_dispatch_rejects_a_tool_outside_the_allowlist() -> None:
    dispatch_mod.init(_config(tools_allowlist=["kb.stats"]))
    with pytest.raises(PermissionDeniedError):
        dispatch("kb.search", lambda timeout_s: ({}, {}))


def test_dispatch_maps_an_app_error_to_a_tool_error_the_model_can_read() -> None:
    from corelib.errors import DependencyError

    dispatch_mod.init(_config())

    def _boom(timeout_s: int) -> tuple[dict[str, object], dict[str, object]]:
        raise DependencyError("embedder unavailable", details={})

    with pytest.raises(ToolError, match="embedder unavailable"):
        dispatch("kb.search", _boom)


def test_dispatch_lets_unexpected_exceptions_propagate_for_the_sdk_to_handle() -> None:
    dispatch_mod.init(_config())

    def _boom(timeout_s: int) -> tuple[dict[str, object], dict[str, object]]:
        raise KeyError("unexpected")

    with pytest.raises(KeyError):
        dispatch("kb.search", _boom)


def test_dispatch_truncates_an_oversized_result() -> None:
    dispatch_mod.init(_config(max_result_bytes=32))
    result = dispatch("kb.search", lambda timeout_s: ({"blob": "x" * 1_000}, {}))
    assert result["meta"]["truncated"] is True


def test_dispatch_logs_the_arguments_the_caller_and_a_summary_of_the_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[object] = []
    monkeypatch.setattr(dispatch_mod, "record_tool_invocation", recorded.append)
    monkeypatch.delenv("AGX_MCP_CALLER", raising=False)
    monkeypatch.setenv("PWD", "/home/u/quant-modeling")
    dispatch_mod.init(_config())
    data = {
        "results": [
            {
                "rank": 1,
                "content": "passage",
                "citation": {"doc_key": "giles-mlmc", "document": "MLMC", "section_path": "2"},
                "scores": {"rerank": 5.2},
            }
        ],
        "warnings": [],
    }
    dispatch("kb.search", lambda t: (data, {"provenance": ["giles-mlmc"]}), args={"text": "MLMC"})
    (inv,) = recorded
    assert inv.args == {"text": "MLMC"}  # type: ignore[attr-defined]
    assert inv.caller == "quant-modeling"  # type: ignore[attr-defined]
    assert inv.result == {  # type: ignore[attr-defined]
        "n_results": 1,
        "hits": [
            {"rank": 1, "doc_key": "giles-mlmc", "document": "MLMC", "section": "2", "rerank": 5.2}
        ],
        "provenance": ["giles-mlmc"],
        "truncated": False,
    }


def test_an_explicit_caller_wins_over_the_working_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PWD", "/home/u/quant-modeling")
    monkeypatch.setenv("AGX_MCP_CALLER", "openhands")
    assert dispatch_mod.caller() == "openhands"


def test_call_args_drops_the_arguments_left_to_none() -> None:
    assert dispatch_mod.call_args({"text": "x", "k": None, "rerank": False}) == {
        "text": "x",
        "rerank": False,
    }
