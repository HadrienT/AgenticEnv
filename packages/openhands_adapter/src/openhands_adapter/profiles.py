"""Agent profiles: `agents/profiles/*.yaml` turned into what an `Agent` gets (WP12 §3).

A profile decides the agent's prompt, its tools and its limits. Reading the files
here, rather than in the bridge, keeps one place that knows what they mean.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from corelib.config import repo_root
from corelib.errors import ConfigError
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

DEFAULT_PROFILE = "coding"

_MAX_REPO_NOTES_BYTES = 16_384
_REPO_NOTES_FILES = ("AGENTS.md", "CLAUDE.md")
# Part of the agent itself: filtering them out would leave it unable to finish.
_ALWAYS_ALLOWED = ("finish", "think", "task_tracker")


class _Filesystem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    read: bool = True


class _Terminal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    execute: bool = False


class _Permissions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    filesystem: _Filesystem = Field(default_factory=_Filesystem)
    terminal: _Terminal = Field(default_factory=_Terminal)


class _Limits(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_iterations: int | None = None
    timeout_seconds: int | None = None


class AgentProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str
    description: str
    system_prompt: str
    mcp_tools: list[str]
    permissions: _Permissions = Field(default_factory=_Permissions)
    limits: _Limits = Field(default_factory=_Limits)

    @property
    def builtin_tools(self) -> list[str]:
        tools = ["task_tracker"]
        if self.permissions.terminal.execute:
            tools.append("terminal")
        if self.permissions.filesystem.read:
            tools.append("file_editor")
        return tools

    @property
    def tools_regex(self) -> str:
        """The SDK names an MCP tool `<server>_<tool>`, e.g. `kbase_kb.search`."""
        builtin = [*_ALWAYS_ALLOWED, *self.builtin_tools]
        names = "|".join(re.escape(name) for name in dict.fromkeys(builtin))
        mcp = "|".join(re.escape(name) for name in self.mcp_tools)
        return f"^(?:{names}|[a-z]+_(?:{mcp}))$"

    def prompt(self) -> str:
        """`system_prompt` lists files joined by ` + `, relative to the repo root."""
        parts = []
        for relative in self.system_prompt.split(" + "):
            path = repo_root() / relative.strip()
            if not path.is_file():
                raise ConfigError(
                    f"profile {self.role}: prompt file not found: {path}",
                    details={"path": str(path)},
                )
            parts.append(path.read_text(encoding="utf-8").strip())
        return "\n\n".join(parts)


def list_profiles() -> list[str]:
    return sorted(path.stem for path in (repo_root() / "agents" / "profiles").glob("*.yaml"))


def load_profile(name: str) -> AgentProfile:
    path = repo_root() / "agents" / "profiles" / f"{name}.yaml"
    if name not in list_profiles():
        raise ConfigError(f"unknown agent profile: {name}", details={"available": list_profiles()})
    try:
        return AgentProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (PydanticValidationError, yaml.YAMLError) as exc:
        raise ConfigError(
            f"invalid agent profile {name}: {exc}", details={"path": str(path)}
        ) from exc


def repo_notes(project: str | None) -> str | None:
    """The target repo's own instructions, for the agent to follow."""
    if project is None:
        return None
    for name in _REPO_NOTES_FILES:
        path = Path(project) / name
        if path.is_file():
            text = path.read_bytes()[:_MAX_REPO_NOTES_BYTES].decode("utf-8", "ignore")
            return f'<repository_instructions source="{name}">\n{text}\n</repository_instructions>'
    return None
