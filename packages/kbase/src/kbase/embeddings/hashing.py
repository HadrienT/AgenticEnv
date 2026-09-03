"""`HashingEmbedder`: the local, offline `Embedder` implementation delivered by WP04.

This is a deterministic feature-hashing bag-of-words embedding, **not** a semantic
model — it exists so the ingestion pipeline (and WP05's retrieval layer) have a
concrete, dependency-free, fully offline `Embedder` to write and test against.
Swapping in a real sentence embedding model later is a config change
(`configs/kbase.yaml → embeddings.provider/model_name`) plus a new `Embedder`
implementation; `kb.chunk_embeddings`'s composite PK already supports both
coexisting during a `kbase reindex --model <name>` migration (WP04 §9).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


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

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in _TOKEN_RE.findall(text.lower()):
            index, sign = _token_bucket(token, self.dim)
            vector[index] += sign
        if self._normalize:
            norm = math.sqrt(sum(v * v for v in vector))
            if norm > 0.0:
                vector = [v / norm for v in vector]
        return vector

    def embed_documents(self, texts: Sequence[str]) -> list[Sequence[float]]:
        return [self._embed_one(text) for text in texts]

    def embed_query(self, text: str) -> Sequence[float]:
        return self._embed_one(text)
