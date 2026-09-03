from __future__ import annotations

import pytest
from agentmem_mcp.policy import check_allowlisted, resolve_timeout_s, truncate_data
from agentmem_mcp.schemas import McpServerConfig
from corelib.errors import PermissionDeniedError


def _config(**overrides: object) -> McpServerConfig:
    defaults: dict[str, object] = {
        "name": "agentmem",
        "tools_allowlist": ["mem.recall"],
        "default_timeout_s": 30,
    }
    defaults.update(overrides)
    return McpServerConfig.model_validate(defaults)


def test_check_allowlisted_passes_for_a_listed_tool() -> None:
    check_allowlisted(_config(), "mem.recall")


def test_check_allowlisted_rejects_an_unlisted_tool() -> None:
    with pytest.raises(PermissionDeniedError):
        check_allowlisted(_config(), "mem.remember")


def test_resolve_timeout_s_falls_back_to_the_server_default() -> None:
    config = _config(default_timeout_s=45)
    assert resolve_timeout_s(config, "mem.recall") == 45


def test_resolve_timeout_s_uses_the_per_tool_override() -> None:
    config = _config(default_timeout_s=45, per_tool_timeout_s={"mem.recall": 15})
    assert resolve_timeout_s(config, "mem.recall") == 15


def test_truncate_data_leaves_small_payloads_untouched() -> None:
    data = {"ok": True}
    payload, truncated = truncate_data(data, max_bytes=1_000)
    assert payload == data
    assert truncated is False


def test_truncate_data_replaces_oversized_payloads() -> None:
    data = {"blob": "x" * 1_000}
    payload, truncated = truncate_data(data, max_bytes=64)
    assert truncated is True
    assert payload is not None
    assert payload["truncated"] is True


def test_truncate_data_passes_through_none() -> None:
    payload, truncated = truncate_data(None, max_bytes=64)
    assert payload is None
    assert truncated is False
