"""Embedders for episode text: `HttpEmbedder` for a real model behind a local
`llama-server --embedding`, `HashingEmbedder` for tests and offline use.

Deliberately **not** imported from `kbase.embeddings` even though the algorithms are
identical: `agentmem` (experience) and `kbase` (knowledge) are kept architecturally
decoupled (00-PRIMER.md §3, §6; import-linter contract D10 forbids `agentmem -> kbase`).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from corelib.errors import ConfigError, DependencyError

from agentmem.config import EmbeddingsConfig

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_TIMEOUT_S = 30.0


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


class HttpEmbedder:
    def __init__(self, *, base_url: str, model_name: str, model_version: str, dim: int) -> None:
        self.model_name = model_name
        self.model_version = model_version
        self.dim = dim
        self._url = f"{base_url.rstrip('/')}/embeddings"

    def embed(self, text: str) -> list[float]:
        request = urllib.request.Request(
            self._url,
            data=json.dumps({"model": self.model_name, "input": [text]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
                vector = [float(v) for v in json.load(response)["data"][0]["embedding"]]
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as exc:
            raise DependencyError(f"{self._url}: {exc}", details={"url": self._url}) from exc
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm > 0.0 else vector


def build_embedder(config: EmbeddingsConfig) -> Embedder:
    if config.provider == "local":
        return HashingEmbedder(dim=config.dim, normalize=config.normalize)
    if config.provider == "http" and config.base_url:
        return HttpEmbedder(
            base_url=config.base_url,
            model_name=config.model_name,
            model_version=config.model_version,
            dim=config.dim,
        )
    raise ConfigError(
        f"cannot build embedder {config.provider!r}: needs local, or http with a base_url",
        details={"provider": config.provider},
    )
