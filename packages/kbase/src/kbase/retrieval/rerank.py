"""`Reranker` extension point + a local, offline placeholder implementation.

Like `HashingEmbedder`, `LexicalOverlapReranker` is deliberately not a real
cross-encoder — no such model is available/verified on this dev box. It scores
candidates by token overlap with the query (Jaccard), which is deterministic and
dependency-free. A real cross-encoder is a config change plus a new `Reranker`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

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
