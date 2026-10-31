"""Typed view of `configs/openhands.yaml` (WP08b).

The served model name itself is NOT duplicated here: it comes from
`corelib.config.get_settings().llm.served_model` (single source of truth,
`configs/models.yaml` -> `AGX_LLM_SERVED_MODEL`), exactly like the host-side
`AGX_LLM_BASE_URL`. This file only carries knobs specific to running OpenHands
inside a Docker sandbox: which image, which base_url is reachable *from inside
the container*, and run limits.
"""

from __future__ import annotations

from corelib.config import load_yaml_config
from pydantic import BaseModel, ConfigDict, Field


class SandboxConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    image: str
    platform: str
    enable_gpu: bool
    working_dir: str
    memory: str | None = None
    cpus: int | None = None
    pids_limit: int | None = None
    # Basename globs hidden from the sandbox; `!` keeps a name a glob would catch.
    mask: list[str] = Field(default_factory=list)
    code_tools: bool = False
    host_network: bool = False
    # One long-lived sandbox per project, holding several conversations that survive a
    # reconnect or a bridge restart (WP08e). Off until checked on a real container.
    persistent_conversations: bool = False


class SandboxMcpConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bind_host: str = "172.17.0.1"
    sandbox_host: str = "host.docker.internal"


class SandboxLLMConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Base URL for the OpenAI-compatible endpoint, as reachable from *inside*
    # the agent-server container (via host.docker.internal + the llama-bridge
    # proxy) -- distinct from AGX_LLM_BASE_URL, which is host-side (127.0.0.1).
    sandbox_base_url: str
    # Token streaming to the client.
    stream: bool = False


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_iterations: int
    timeout_s: int


class OpenHandsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sandbox: SandboxConfig
    mcp: SandboxMcpConfig = Field(default_factory=SandboxMcpConfig)
    llm: SandboxLLMConfig
    run: RunConfig


def load_openhands_config() -> OpenHandsConfig:
    return load_yaml_config("openhands.yaml", OpenHandsConfig)
