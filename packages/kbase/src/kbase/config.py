"""Typed view of `configs/kbase.yaml` (ingestion + retrieval, WP04 + WP05)."""

from __future__ import annotations

import os
from typing import Literal

from corelib.config import load_yaml_config
from pydantic import BaseModel, ConfigDict, field_validator

from kbase.schemas import COLLECTIONS


class EmbeddingsConfig(BaseModel):
    provider: str
    model_name: str
    model_version: str
    dim: int
    batch_size: int
    normalize: bool
    base_url: str | None = None
    timeout_s: float = 60.0
    # Embed "document title / section path / content" instead of the content alone.
    contextual: bool = False
    # Asymmetric models (Qwen3-Embedding) want queries as "Instruct: …\nQuery: …".
    query_instruction: str | None = None
    # Keep the first `dim` dimensions of a larger Matryoshka model (needs normalize).
    truncate_dim: bool = False
    # Characters sent per input; keeps any chunk under the server's batch size.
    max_input_chars: int | None = None


class ChunkingConfig(BaseModel):
    strategy: str
    target_tokens: int
    max_tokens: int
    overlap_tokens: int
    keep_equation_with_context: bool
    never_split_within: list[str]
    min_tokens: int = 0


class RerankConfig(BaseModel):
    provider: str
    model_name: str
    top_k: int
    # How many fused candidates the reranker sees: with no more than `k`, it can only
    # reorder what fusion already picked.
    candidates: int
    base_url: str | None = None
    timeout_s: float = 30.0
    # The cross-encoder reads "document title / section path / content" (WP19: +4 points
    # of passage MRR over the content alone).
    contextual: bool = False
    max_document_chars: int | None = None


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
    # At most this many chunks of one document in a result: a long book otherwise
    # fills the top-k with near-duplicates of one answer.
    max_chunks_per_document: int | None = None
    # pgvector's default (40) caps an HNSW scan below `candidates_vector`.
    hnsw_ef_search: int | None = None
    # pgvector >= 0.8: keep scanning the HNSW graph until enough rows pass the filters.
    # Without it a selective filter (one collection, one topic) silently loses recall,
    # because the filter is applied after a scan of `ef_search` neighbours (WP20 §3.2).
    # Ignored, with a warning in the result, on an older pgvector.
    hnsw_iterative_scan: Literal["relaxed_order", "strict_order"] | None = None
    hnsw_max_scan_tuples: int | None = None


class CollectionConfig(BaseModel):
    """One corpus the agent can search (WP20 §2); `description` is what the model reads
    when it picks one."""

    description: str


_DEFAULT_COLLECTIONS: dict[str, CollectionConfig] = {
    "quant": CollectionConfig(
        description=(
            "derivatives pricing and its numerical methods: stochastic and rough volatility, "
            "Monte Carlo/QMC, PDE, Fourier, AAD, calibration, XVA pricing, C++/CUDA performance"
        )
    ),
    "regulation": CollectionConfig(
        description=(
            "prudential regulation and supervisory texts: Basel Framework (BCBS), CRR/CRD, "
            "EBA; capital rules for market risk (FRTB), counterparty credit risk (SA-CCR, "
            "IMM), CVA capital, credit risk, liquidity, model risk"
        )
    ),
}


class CurationConfig(BaseModel):
    """Section titles (regexes, see `ingestion.curation`) never ingested."""

    drop_sections: list[str] = []


class ProvenanceConfig(BaseModel):
    require_page: bool
    require_section: bool


class IngestionConfig(BaseModel):
    max_file_size_mb: int
    parse_timeout_s: int
    # A book takes MinerU a long time, and is far bigger than a Markdown source.
    pdf_max_file_size_mb: int = 500
    pdf_timeout_s: int = 7200
    mineru_binary: str = ".mineru-venv/bin/mineru"
    mineru_adapter: str = "documents/mineru_adapter.py"
    mineru_cache_dir: str = "documents/parsed"


class HarvestConfig(BaseModel):
    """arXiv harvest (WP18). Paths are relative to AGX_PATHS_DOCUMENTS_DIR, except the
    manifest, which is versioned in the repo like `documents/manifest.yaml`."""

    user_agent: str = "AgenticEnv-kbase-harvest/0.1 (+https://github.com/HadrienT/AgenticEnv)"
    min_interval_s: float = 3.0  # arXiv API terms: one request every 3 seconds
    max_attempts: int = 4
    timeout_s: float = 60.0
    page_size: int = 100
    min_text_chars: int = 1500
    html_dir: str = "arxiv/html"
    md_dir: str = "arxiv/md"
    manifest: str = "documents/manifest-arxiv.yaml"
    known_manifests: list[str] = ["documents/manifest.yaml"]


class BaselHarvestConfig(BaseModel):
    """Basel Framework chapters from bis.org (WP20 §5.1). A generic user agent: nothing
    identifying the maintainer goes to a third-party site."""

    user_agent: str = "kbase-harvest/0.1 (local research index; low request rate)"
    min_interval_s: float = 3.0
    max_attempts: int = 4
    timeout_s: float = 60.0
    # Any chapter page lists every chapter; robots.txt disallows the standard index pages.
    seed_url: str = (
        "https://www.bis.org/committees/bcbs/basel-framework/standard/sco/10"
        "/inforce/2019-12-15/published/2019-12-15"
    )
    html_dir: str = "basel/html"
    md_dir: str = "basel/md"
    pdf_dir: str = "basel/pdf"
    manifest: str = "documents/manifest-regulation.yaml"


class KbaseConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    embeddings: EmbeddingsConfig
    chunking: ChunkingConfig
    retrieval: RetrievalConfig
    provenance: ProvenanceConfig
    ingestion: IngestionConfig
    curation: CurationConfig = CurationConfig()
    harvest: HarvestConfig = HarvestConfig()
    basel: BaselHarvestConfig = BaselHarvestConfig()
    collections: dict[str, CollectionConfig] = _DEFAULT_COLLECTIONS

    @field_validator("collections")
    @classmethod
    def _known_collections(cls, value: dict[str, CollectionConfig]) -> dict[str, CollectionConfig]:
        unknown = sorted(set(value) - set(COLLECTIONS))
        if unknown:
            raise ValueError(f"unknown collection(s) {unknown}: declare them in kbase.schemas")
        return value


def load_kbase_config() -> KbaseConfig:
    """`AGX_KBASE_CONFIG` picks another file of `configs/`, e.g. `kbase-bge.yaml`."""
    return load_yaml_config(os.environ.get("AGX_KBASE_CONFIG", "kbase.yaml"), KbaseConfig)
