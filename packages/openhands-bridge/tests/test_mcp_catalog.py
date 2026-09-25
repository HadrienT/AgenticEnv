from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from corelib.config import reset_settings_cache
from corelib.errors import ConfigError
from openhands_bridge.mcp_catalog import list_mcp_servers

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
