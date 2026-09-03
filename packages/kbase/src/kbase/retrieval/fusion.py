"""Reciprocal Rank Fusion (WP05 §4): `score(d) = sum_b 1 / (rrf_k + rank_b(d))`.

RRF needs no score normalization across branches of different nature (cosine
distance vs `ts_rank`), which is exactly the mismatch between vector and lexical.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RankedHit:
    chunk_id: str
    score: float


def reciprocal_rank_fusion(
    vector_hits: Sequence[RankedHit],
    lexical_hits: Sequence[RankedHit],
    *,
    rrf_k: int,
) -> dict[str, dict[str, float]]:
    """`vector_hits`/`lexical_hits` must already be sorted best-first by their branch."""
    scores: dict[str, dict[str, float]] = {}
    for rank, hit in enumerate(vector_hits, start=1):
        entry = scores.setdefault(hit.chunk_id, {})
        entry["vector"] = hit.score
        entry["fused"] = entry.get("fused", 0.0) + 1.0 / (rrf_k + rank)
    for rank, hit in enumerate(lexical_hits, start=1):
        entry = scores.setdefault(hit.chunk_id, {})
        entry["lexical"] = hit.score
        entry["fused"] = entry.get("fused", 0.0) + 1.0 / (rrf_k + rank)
    return scores


def rank_single_branch(
    hits: Sequence[RankedHit], branch: Literal["vector", "lexical"]
) -> dict[str, dict[str, float]]:
    """Pure `vector` or `lexical` strategy: no fusion, but a comparable `fused` score."""
    result: dict[str, dict[str, float]] = {}
    for rank, hit in enumerate(hits, start=1):
        result[hit.chunk_id] = {branch: hit.score, "fused": 1.0 / rank}
    return result
