"""`HttpEmbedder`: a real embedding model behind an OpenAI-compatible endpoint, in
practice a local `llama-server --embedding` (`agenticenv-embed.service`)."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from corelib.errors import DependencyError


def post_json(url: str, payload: dict[str, Any], *, timeout_s: float) -> Any:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise DependencyError(f"{url}: {exc}", details={"url": url}) from exc


class HttpEmbedder:
    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        model_version: str,
        dim: int,
        normalize: bool,
        batch_size: int,
        timeout_s: float,
    ) -> None:
        self.model_name = model_name
        self.model_version = model_version
        self.dim = dim
        self._url = f"{base_url.rstrip('/')}/embeddings"
        self._normalize = normalize
        self._batch_size = batch_size
        self._timeout_s = timeout_s

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        body = post_json(
            self._url, {"model": self.model_name, "input": list(texts)}, timeout_s=self._timeout_s
        )
        rows = sorted(body["data"], key=lambda row: row["index"])
        vectors = [[float(v) for v in row["embedding"]] for row in rows]
        for vector in vectors:
            if len(vector) != self.dim:
                raise DependencyError(
                    f"{self.model_name} returned {len(vector)} dimensions, expected {self.dim}",
                    details={"model": self.model_name},
                )
        return [self._unit(vector) for vector in vectors] if self._normalize else vectors

    @staticmethod
    def _unit(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm > 0.0 else vector

    def embed_documents(self, texts: Sequence[str]) -> list[Sequence[float]]:
        vectors: list[Sequence[float]] = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(self._embed(texts[start : start + self._batch_size]))
        return vectors

    def embed_query(self, text: str) -> Sequence[float]:
        return self._embed([text])[0]
