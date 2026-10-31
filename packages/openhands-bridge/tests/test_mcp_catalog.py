from __future__ import annotations

import socket
from collections.abc import Iterator
from pathlib import Path

import pytest
from corelib.config import reset_settings_cache
from corelib.errors import ConfigError
from openhands_bridge.mcp_catalog import (
    McpServerSummary,
    build_mcp_config,
    list_mcp_servers,
    unavailable_reason,
)

from openhands_adapter import OpenHandsConfig

_REQUIRED_ENV = {
    "AGX_ENV": "dev",
    "AGX_DB_HOST": "127.0.0.1",
    "AGX_DB_PORT": "5432",
    "AGX_DB_NAME": "agenticenv",
    "AGX_DB_USER": "app_rw",
    "AGX_DB_PASSWORD": "secret",
    "AGX_LLM_BASE_URL": "http://127.0.0.1:8000/v1",
    "AGX_LLM_SERVED_MODEL": "Qwen3-Coder-30B-A3B-Instruct",
    "AGX_LLM_CTX_SIZE": "32768",
    "AGX_PATHS_MODELS_DIR": "/opt/llm/models",
    "AGX_PATHS_DOCUMENTS_DIR": "/srv/knowledge/documents",
    "AGX_PATHS_REPOS_DIR": "/srv/repos",
}


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    monkeypatch.chdir(tmp_path)
    for key in _REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)
    for key, value in _REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    reset_settings_cache()
    yield monkeypatch
    reset_settings_cache()


def test_list_mcp_servers_reads_each_yaml_file(
    isolated_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mcp_dir = tmp_path / "configs" / "mcp"
    mcp_dir.mkdir(parents=True)
    (mcp_dir / "kbase.yaml").write_text(
        "name: kbase\ntransport: stdio\ntools_allowlist: [kb.search, kb.stats]\n"
    )
    (mcp_dir / "agentmem.yaml").write_text("name: agentmem\ntransport: stdio\n")
    isolated_env.setenv("AGX_CONFIGS_DIR", str(tmp_path / "configs"))
    reset_settings_cache()

    servers = list_mcp_servers()

    assert [s.name for s in servers] == ["agentmem", "kbase"]
    kbase = next(s for s in servers if s.name == "kbase")
    assert kbase.tools_allowlist == ["kb.search", "kb.stats"]
    agentmem = next(s for s in servers if s.name == "agentmem")
    assert agentmem.tools_allowlist == []


def test_list_mcp_servers_missing_directory_raises_config_error(
    isolated_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolated_env.setenv("AGX_CONFIGS_DIR", str(tmp_path / "configs"))
    reset_settings_cache()

    with pytest.raises(ConfigError):
        list_mcp_servers()


def _config(*, code_tools: bool) -> OpenHandsConfig:
    return OpenHandsConfig.model_validate(
        {
            "sandbox": {
                "image": "x",
                "platform": "linux/amd64",
                "enable_gpu": False,
                "working_dir": "/workspace",
                "code_tools": code_tools,
            },
            "mcp": {"bind_host": "127.0.0.1", "sandbox_host": "host.docker.internal"},
            "llm": {"sandbox_base_url": "http://x/v1"},
            "run": {"max_iterations": 1, "timeout_s": 1},
        }
    )


def _write_servers(env: pytest.MonkeyPatch, root: Path, port: int) -> None:
    mcp_dir = root / "configs" / "mcp"
    mcp_dir.mkdir(parents=True)
    (mcp_dir / "kbase.yaml").write_text(
        f"name: kbase\ntransport: stdio\nreach: host_http\nport: {port}\n"
    )
    (mcp_dir / "cppdev.yaml").write_text("name: cppdev\ntransport: stdio\nreach: sandbox_stdio\n")
    env.setenv("AGX_CONFIGS_DIR", str(root / "configs"))
    env.setenv("XDG_STATE_HOME", str(root / "state"))
    reset_settings_cache()


def test_host_server_is_called_over_http_with_the_token(
    isolated_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        _write_servers(isolated_env, tmp_path, port)

        config, unavailable = build_mcp_config([], _config(code_tools=False))

    entry = config["mcpServers"]["kbase"]  # type: ignore[index]
    assert entry["url"] == f"http://host.docker.internal:{port}/mcp"
    assert entry["headers"]["Authorization"].startswith("Bearer ")
    assert unavailable == ["cppdev"]


def test_a_server_that_is_down_is_reported_not_fatal(
    isolated_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_servers(isolated_env, tmp_path, 1)

    config, unavailable = build_mcp_config(["kbase"], _config(code_tools=False))

    assert config == {}
    assert unavailable == ["kbase"]


def test_code_servers_run_inside_the_sandbox_when_the_image_has_them(
    isolated_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_servers(isolated_env, tmp_path, 1)

    config, _ = build_mcp_config(["cppdev"], _config(code_tools=True))

    entry = config["mcpServers"]["cppdev"]  # type: ignore[index]
    assert entry["command"].endswith("/cppdev-mcp")
    assert entry["env"]["AGX_REPO_ROOT"] == "/opt/agenticenv"


def test_the_reason_a_code_server_is_unavailable_names_the_setting() -> None:
    server = McpServerSummary(name="cppdev", transport="stdio", reach="sandbox_stdio")

    assert "code_tools" in (unavailable_reason(server, _config(code_tools=False)) or "")
    assert unavailable_reason(server, _config(code_tools=True)) is None
