"""`HashingEmbedder`: the local, offline embedder for episode text.

Deliberately **not** imported from `kbase.embeddings.hashing` even though the
algorithm is identical: `agentmem` (experience) and `kbase` (knowledge) are kept
architecturally decoupled (00-PRIMER.md §3, §6; import-linter contract D10
forbids `agentmem -> kbase`). Same rationale as WP04's `HashingEmbedder`: a
deterministic, dependency-free placeholder — a real sentence embedding model is
a future config + implementation swap (`configs/agentmem.yaml -> embeddings.*`).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


@runtime_checkable
class Embedder(Protocol):
    model_name: str
    model_version: str
    dim: int

    def embed(self, text: str) -> Sequence[float]: ...


def _token_bucket(token: str, dim: int) -> tuple[int, float]:
    """Feature-hashing trick: stable index + sign, avoids a vocabulary/model file."""
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, byteorder="big")
    index = value % dim
    sign = 1.0 if (value >> 63) & 1 == 0 else -1.0
    return index, sign


class HashingEmbedder:
    model_name = "hashing-bow"
    model_version = "1"

    def __init__(self, *, dim: int, normalize: bool = True) -> None:
        self.dim = dim
        self._normalize = normalize

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in _TOKEN_RE.findall(text.lower()):
            index, sign = _token_bucket(token, self.dim)
            vector[index] += sign
        if self._normalize:
            norm = math.sqrt(sum(v * v for v in vector))
            if norm > 0.0:
                vector = [v / norm for v in vector]
        return vector
