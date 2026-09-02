from __future__ import annotations

import threading
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, SecretStr
from pydantic import ValidationError as PydanticValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from corelib.errors import ConfigError


class DatabaseSettings(BaseModel):
    host: str
    port: int
    database: str
    user: str
    password: SecretStr
    statement_timeout_ms: int


class LLMSettings(BaseModel):
    base_url: str
    served_model: str
    ctx_size: int
    request_timeout_s: int


class PathSettings(BaseModel):
    models_dir: Path
    documents_dir: Path
    logs_dir: Path
    repos_dir: Path
    datasets_dir: Path


class Settings(BaseSettings):
    """Root settings. The only module outside `corelib.config` may read env/YAML."""

    model_config = SettingsConfigDict(env_prefix="AGX_", env_file=".env", extra="ignore")

    env: Literal["dev", "prod"]
    log_level: str = "INFO"
    configs_dir: Path = Path("configs")
    migrations_dir: Path = Path("migrations")

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: SecretStr
    db_statement_timeout_ms: int = 30_000

    llm_base_url: str
    llm_served_model: str
    llm_ctx_size: int
    llm_request_timeout_s: int = 120

    paths_models_dir: Path
    paths_documents_dir: Path
    paths_logs_dir: Path = Path("/opt/llm/logs")
    paths_repos_dir: Path
    paths_datasets_dir: Path = Path("/srv/knowledge/datasets")

    @property
    def database(self) -> DatabaseSettings:
        return DatabaseSettings(
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            user=self.db_user,
            password=self.db_password,
            statement_timeout_ms=self.db_statement_timeout_ms,
        )

    @property
    def llm(self) -> LLMSettings:
        return LLMSettings(
            base_url=self.llm_base_url,
            served_model=self.llm_served_model,
            ctx_size=self.llm_ctx_size,
            request_timeout_s=self.llm_request_timeout_s,
        )

    @property
    def paths(self) -> PathSettings:
        return PathSettings(
            models_dir=self.paths_models_dir,
            documents_dir=self.paths_documents_dir,
            logs_dir=self.paths_logs_dir,
            repos_dir=self.paths_repos_dir,
            datasets_dir=self.paths_datasets_dir,
        )


_settings_lock = threading.Lock()
_settings_singleton: Settings | None = None


def get_settings() -> Settings:
    """Thread-safe singleton; raises `ConfigError` naming any missing variable."""
    global _settings_singleton
    if _settings_singleton is not None:
        return _settings_singleton
    with _settings_lock:
        if _settings_singleton is None:
            try:
                _settings_singleton = Settings()
            except PydanticValidationError as exc:
                missing = [".".join(str(p) for p in err["loc"]) for err in exc.errors()]
                raise ConfigError(
                    f"invalid or missing configuration: {', '.join(missing)}",
                    details={"fields": missing},
                ) from exc
    return _settings_singleton


def reset_settings_cache() -> None:
    """Test-only hook: forces the next `get_settings()` call to rebuild from the environment."""
    global _settings_singleton
    with _settings_lock:
        _settings_singleton = None


def load_yaml_config[T: BaseModel](name: str, model: type[T]) -> T:
    """Loads `<configs_dir>/<name>` and validates it against the caller-supplied `model`."""
    if ".." in name or Path(name).is_absolute():
        raise ConfigError(f"invalid config name: {name}", details={"name": name})
    settings = get_settings()
    path = settings.configs_dir / name
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}", details={"path": str(path)})
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    try:
        return model.model_validate(raw)
    except PydanticValidationError as exc:
        raise ConfigError(
            f"invalid config file {path}: {exc}", details={"path": str(path)}
        ) from exc
