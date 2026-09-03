"""`HybridRetriever`: the sole public entry point for WP05 (blueprint 03-INTERFACES.md
§3.5, 05-SEQUENCES.md §9). Orchestrates filters -> vector/lexical search -> RRF fusion
-> provenance -> optional reranking -> contradiction detection -> `kb.retrieval_logs`.
"""

from __future__ import annotations

import time

from corelib.db import session_scope
from corelib.errors import DependencyError
from corelib.ids import new_id
from corelib.logging import get_logger

from kbase.embeddings.base import Embedder
from kbase.provenance import assert_complete, build_citation
from kbase.retrieval import contradictions, fusion, lexical, logs, store, vector
from kbase.retrieval.filters import to_sql_predicate
from kbase.retrieval.query import RetrievalQuery, RetrievalResult
from kbase.retrieval.rerank import Reranker
from kbase.schemas import RetrievedChunk

logger = get_logger(__name__)


class HybridRetriever:
    def __init__(
        self,
        *,
        embedder: Embedder,
        reranker: Reranker | None,
        candidates_vector: int,
        candidates_lexical: int,
        rrf_k: int,
        fts_config: str,
        min_score: float,
        rerank_top_k: int,
        require_page: bool,
        require_section: bool,
    ) -> None:
        self._embedder = embedder
        self._reranker = reranker
        self._candidates_vector = candidates_vector
        self._candidates_lexical = candidates_lexical
        self._rrf_k = rrf_k
        self._fts_config = fts_config
        self._min_score = min_score
        self._rerank_top_k = rerank_top_k
        self._require_page = require_page
        self._require_section = require_section

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        started = time.monotonic()
        correlation_id = new_id()
        predicate_sql, predicate_params = to_sql_predicate(query.filters)
        warnings: list[str] = []

        with session_scope() as session:
            vector_hits: list[fusion.RankedHit] = []
            lexical_hits: list[fusion.RankedHit] = []

            if query.strategy in ("hybrid", "vector"):
                try:
                    embedding = self._embedder.embed_query(query.text)
                except Exception as exc:
                    raise DependencyError(
                        f"embedder unavailable: {exc}", details={"strategy": query.strategy}
                    ) from exc
                vector_hits = vector.search(
                    session,
                    embedding=embedding,
                    model_name=self._embedder.model_name,
                    model_version=self._embedder.model_version,
                    predicate_sql=predicate_sql,
                    predicate_params=predicate_params,
                    candidates_n=self._candidates_vector,
                )

            if query.strategy in ("hybrid", "lexical"):
                lexical_hits = lexical.search(
                    session,
                    query_text=query.text,
                    fts_config=self._fts_config,
                    predicate_sql=predicate_sql,
                    predicate_params=predicate_params,
                    candidates_n=self._candidates_lexical,
                )

            if query.strategy == "hybrid":
                fused = fusion.reciprocal_rank_fusion(vector_hits, lexical_hits, rrf_k=self._rrf_k)
            elif query.strategy == "vector":
                fused = fusion.rank_single_branch(vector_hits, "vector")
            else:
                fused = fusion.rank_single_branch(lexical_hits, "lexical")

            ranked_ids = sorted(fused, key=lambda cid: fused[cid]["fused"], reverse=True)
            ranked_ids = [cid for cid in ranked_ids if fused[cid]["fused"] >= self._min_score]

            pool_size = query.k
            if query.rerank and self._reranker is not None:
                pool_size = max(query.k, self._rerank_top_k)
            candidate_ids = ranked_ids[:pool_size]

            candidates = store.load_candidates(session, candidate_ids)
            retrieved: list[RetrievedChunk] = []
            for rank, chunk_id in enumerate(candidate_ids, start=1):
                if chunk_id not in candidates:
                    continue
                chunk, meta = candidates[chunk_id]
                citation = build_citation(chunk, meta)
                assert_complete(
                    citation,
                    require_page=self._require_page,
                    require_section=self._require_section,
                )
                retrieved.append(
                    RetrievedChunk(
                        chunk=chunk, citation=citation, scores=dict(fused[chunk_id]), rank=rank
                    )
                )

        if query.rerank and self._reranker is not None and retrieved:
            try:
                retrieved = self._reranker.rerank(query.text, retrieved, top_k=query.k)
            except Exception as exc:
                logger.warning("reranker %s unavailable: %s", self._reranker.model_name, exc)
                warnings.append(f"reranker unavailable ({exc}); returning fused ranking")
                retrieved = retrieved[: query.k]
        else:
            retrieved = retrieved[: query.k]

        warnings.extend(contradictions.detect(retrieved))

        result = RetrievalResult(
            query=query,
            chunks=retrieved,
            total_candidates=len(ranked_ids),
            strategy_used=query.strategy,
            latency_ms=int((time.monotonic() - started) * 1000),
            correlation_id=correlation_id,
            warnings=warnings,
        )

        with session_scope() as session:
            logs.record(session, result)

        return result
