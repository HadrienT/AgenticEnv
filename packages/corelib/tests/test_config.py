from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from corelib.config import get_settings, load_yaml_config, reset_settings_cache
from corelib.errors import ConfigError
from pydantic import BaseModel

REQUIRED_ENV = {
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


@pytest.fixture()
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """No .env file in cwd; only explicitly-set env vars are visible to Settings."""
    monkeypatch.chdir(tmp_path)
    for key in REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)
    reset_settings_cache()
    yield monkeypatch
    reset_settings_cache()


def _set_all_required(env: pytest.MonkeyPatch, *, skip: str | None = None) -> None:
    for key, value in REQUIRED_ENV.items():
        if key != skip:
            env.setenv(key, value)


def test_get_settings_raises_config_error_naming_missing_variable(
    isolated_env: pytest.MonkeyPatch,
) -> None:
    _set_all_required(isolated_env, skip="AGX_DB_PASSWORD")
    with pytest.raises(ConfigError) as exc_info:
        get_settings()
    assert "db_password" in str(exc_info.value.details["fields"])


def test_get_settings_succeeds_with_all_required_variables(
    isolated_env: pytest.MonkeyPatch,
) -> None:
    _set_all_required(isolated_env)
    settings = get_settings()
    assert settings.database.host == "127.0.0.1"
    assert settings.llm.ctx_size == 32768


def test_env_var_overrides_pydantic_default(isolated_env: pytest.MonkeyPatch) -> None:
    _set_all_required(isolated_env)
    isolated_env.setenv("AGX_LOG_LEVEL", "DEBUG")
    assert get_settings().log_level == "DEBUG"


def test_default_used_when_env_var_absent(isolated_env: pytest.MonkeyPatch) -> None:
    _set_all_required(isolated_env)
    assert get_settings().log_level == "INFO"


def test_secret_not_revealed_by_model_dump_or_repr(isolated_env: pytest.MonkeyPatch) -> None:
    _set_all_required(isolated_env)
    database = get_settings().database
    assert database.model_dump()["password"] != "secret"
    assert "secret" not in repr(database.password)


class _SampleConfig(BaseModel):
    value: int


def test_load_yaml_config_validates_against_supplied_model(
    isolated_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_all_required(isolated_env)
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "sample.yaml").write_text("value: 42\n")
    isolated_env.setenv("AGX_CONFIGS_DIR", str(configs_dir))

    result = load_yaml_config("sample.yaml", _SampleConfig)
    assert result.value == 42


def test_load_yaml_config_missing_file_raises_config_error(
    isolated_env: pytest.MonkeyPatch,
) -> None:
    _set_all_required(isolated_env)
    with pytest.raises(ConfigError):
        load_yaml_config("missing.yaml", _SampleConfig)


def test_load_yaml_config_rejects_path_traversal(isolated_env: pytest.MonkeyPatch) -> None:
    _set_all_required(isolated_env)
    with pytest.raises(ConfigError):
        load_yaml_config("../etc/passwd", _SampleConfig)
