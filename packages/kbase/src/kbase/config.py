"""Typed view of `configs/kbase.yaml` (ingestion + retrieval, WP04 + WP05)."""

from __future__ import annotations

import os

from corelib.config import load_yaml_config
from pydantic import BaseModel, ConfigDict


class EmbeddingsConfig(BaseModel):
    provider: str
    model_name: str
    model_version: str
    dim: int
    batch_size: int
    normalize: bool
    base_url: str | None = None
    timeout_s: float = 60.0


class ChunkingConfig(BaseModel):
    strategy: str
    target_tokens: int
    max_tokens: int
    overlap_tokens: int
    keep_equation_with_context: bool
    never_split_within: list[str]


class RerankConfig(BaseModel):
    provider: str
    model_name: str
    top_k: int
    # How many fused candidates the reranker sees: with no more than `k`, it can only
    # reorder what fusion already picked.
    candidates: int
    base_url: str | None = None
    timeout_s: float = 30.0


class RetrievalConfig(BaseModel):
    default_k: int
    candidates_vector: int
    candidates_lexical: int
    fusion: str
    rrf_k: int
    rerank: RerankConfig
    fts_config: str
    lexical_fallback: bool = True
    min_score: float


class ProvenanceConfig(BaseModel):
    require_page: bool
    require_section: bool


class IngestionConfig(BaseModel):
    max_file_size_mb: int
    parse_timeout_s: int


class KbaseConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    embeddings: EmbeddingsConfig
    chunking: ChunkingConfig
    retrieval: RetrievalConfig
    provenance: ProvenanceConfig
    ingestion: IngestionConfig


def load_kbase_config() -> KbaseConfig:
    """`AGX_KBASE_CONFIG` picks another file of `configs/`, e.g. `kbase-bge.yaml`."""
    return load_yaml_config(os.environ.get("AGX_KBASE_CONFIG", "kbase.yaml"), KbaseConfig)
