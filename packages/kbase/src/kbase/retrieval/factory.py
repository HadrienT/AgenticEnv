"""Builds the retriever a config describes: the only place that picks implementations,
so the CLI, the MCP server and `kbase eval` always search the same way."""

from __future__ import annotations

from corelib.errors import ConfigError

from kbase.config import EmbeddingsConfig, KbaseConfig, RerankConfig
from kbase.embeddings.base import Embedder
from kbase.embeddings.hashing import HashingEmbedder
from kbase.embeddings.http import HttpEmbedder
from kbase.retrieval.hybrid import HybridRetriever
from kbase.retrieval.rerank import HttpReranker, LexicalOverlapReranker, Reranker


def build_embedder(config: EmbeddingsConfig) -> Embedder:
    if config.provider == "local":
        return HashingEmbedder(dim=config.dim, normalize=config.normalize)
    if config.provider == "http" and config.base_url:
        return HttpEmbedder(
            base_url=config.base_url,
            model_name=config.model_name,
            model_version=config.model_version,
            dim=config.dim,
            normalize=config.normalize,
            batch_size=config.batch_size,
            timeout_s=config.timeout_s,
        )
    raise ConfigError(
        f"cannot build embedder {config.provider!r}: needs local, or http with a base_url",
        details={"provider": config.provider},
    )


def build_reranker(config: RerankConfig) -> Reranker | None:
    if config.provider == "none":
        return None
    if config.provider == "lexical":
        return LexicalOverlapReranker()
    if config.provider == "http" and config.base_url:
        return HttpReranker(
            base_url=config.base_url, model_name=config.model_name, timeout_s=config.timeout_s
        )
    raise ConfigError(
        f"cannot build reranker {config.provider!r}: needs none, lexical, or http with a base_url",
        details={"provider": config.provider},
    )


def build_retriever(config: KbaseConfig) -> HybridRetriever:
    return HybridRetriever(
        embedder=build_embedder(config.embeddings),
        reranker=build_reranker(config.retrieval.rerank),
        candidates_vector=config.retrieval.candidates_vector,
        candidates_lexical=config.retrieval.candidates_lexical,
        rrf_k=config.retrieval.rrf_k,
        fts_config=config.retrieval.fts_config,
        min_score=config.retrieval.min_score,
        rerank_top_k=config.retrieval.rerank.candidates,
        require_page=config.provenance.require_page,
        require_section=config.provenance.require_section,
        lexical_fallback=config.retrieval.lexical_fallback,
    )
