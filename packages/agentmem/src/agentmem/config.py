"""Typed view of `configs/agentmem.yaml` (WP07 §4/§5, 06-CONFIG.md `configs/agentmem.yaml`)."""

from __future__ import annotations

import os

from corelib.config import load_yaml_config
from pydantic import BaseModel, ConfigDict


class EmbeddingsConfig(BaseModel):
    provider: str = "local"
    base_url: str | None = None
    model_name: str
    model_version: str
    dim: int
    normalize: bool


class EpisodicConfig(BaseModel):
    embed_summary: bool
    recall_default_k: int
    min_similarity: float


class ProceduralConfig(BaseModel):
    source_dir: str
    sync_on_start: bool


class AgentmemConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    embeddings: EmbeddingsConfig
    episodic: EpisodicConfig
    procedural: ProceduralConfig


def load_agentmem_config() -> AgentmemConfig:
    """`AGX_AGENTMEM_CONFIG` picks another file of `configs/`, e.g. `agentmem-bge.yaml`."""
    return load_yaml_config(os.environ.get("AGX_AGENTMEM_CONFIG", "agentmem.yaml"), AgentmemConfig)
