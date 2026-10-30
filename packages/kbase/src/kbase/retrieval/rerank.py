"""`Reranker` extension point. `HttpReranker` is the real cross-encoder, behind a
local `llama-server --reranking`. `LexicalOverlapReranker` scores by token overlap
(Jaccard): deterministic and offline, for tests, but it favours short chunks.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from kbase.embeddings.http import post_json
from kbase.schemas import RetrievedChunk

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text)}


@runtime_checkable
class Reranker(Protocol):
    model_name: str

    def rerank(
        self, query: str, candidates: Sequence[RetrievedChunk], *, top_k: int
    ) -> list[RetrievedChunk]: ...


class HttpReranker:
    def __init__(self, *, base_url: str, model_name: str, timeout_s: float) -> None:
        self.model_name = model_name
        self._url = f"{base_url.rstrip('/')}/rerank"
        self._timeout_s = timeout_s

    def rerank(
        self, query: str, candidates: Sequence[RetrievedChunk], *, top_k: int
    ) -> list[RetrievedChunk]:
        body = post_json(
            self._url,
            {
                "model": self.model_name,
                "query": query,
                "documents": [c.chunk.content for c in candidates],
            },
            timeout_s=self._timeout_s,
        )
        scored = []
        for row in sorted(body["results"], key=lambda r: r["relevance_score"], reverse=True):
            candidate = candidates[row["index"]]
            scores = {**candidate.scores, "rerank": float(row["relevance_score"])}
            scored.append(candidate.model_copy(update={"scores": scores}))
        for rank, chunk in enumerate(scored[:top_k], start=1):
            chunk.rank = rank
        return scored[:top_k]


class LexicalOverlapReranker:
    model_name = "lexical-overlap"

    def rerank(
        self, query: str, candidates: Sequence[RetrievedChunk], *, top_k: int
    ) -> list[RetrievedChunk]:
        query_tokens = _tokens(query)

        def overlap_score(chunk: RetrievedChunk) -> float:
            content_tokens = _tokens(chunk.chunk.content)
            if not query_tokens or not content_tokens:
                return 0.0
            shared = query_tokens & content_tokens
            union = query_tokens | content_tokens
            return len(shared) / len(union)

        scored = []
        for candidate in candidates:
            score = overlap_score(candidate)
            scores = dict(candidate.scores)
            scores["rerank"] = score
            scored.append(candidate.model_copy(update={"scores": scores}))

        scored.sort(key=lambda c: c.scores["rerank"], reverse=True)
        for rank, chunk in enumerate(scored[:top_k], start=1):
            chunk.rank = rank
        return scored[:top_k]
