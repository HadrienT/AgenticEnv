"""`Embedder` extension point (blueprint/03-INTERFACES.md §3.2)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    model_name: str
    model_version: str
    dim: int

    def embed_documents(self, texts: Sequence[str]) -> list[Sequence[float]]: ...

    def embed_query(self, text: str) -> Sequence[float]: ...
