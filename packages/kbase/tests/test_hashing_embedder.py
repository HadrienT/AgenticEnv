from __future__ import annotations

import math

from kbase.embeddings.hashing import HashingEmbedder


def test_embed_documents_is_deterministic() -> None:
    embedder = HashingEmbedder(dim=64)
    a = embedder.embed_documents(["hello world"])
    b = embedder.embed_documents(["hello world"])
    assert a == b


def test_embed_query_has_configured_dimension() -> None:
    embedder = HashingEmbedder(dim=32)
    vector = embedder.embed_query("some text")
    assert len(vector) == 32


def test_embed_query_is_normalized_when_configured() -> None:
    embedder = HashingEmbedder(dim=32, normalize=True)
    vector = embedder.embed_query("some longer text with many tokens")
    norm = math.sqrt(sum(v * v for v in vector))
    assert math.isclose(norm, 1.0, abs_tol=1e-6) or norm == 0.0


def test_different_texts_yield_different_vectors() -> None:
    embedder = HashingEmbedder(dim=64)
    a = embedder.embed_query("alpha")
    b = embedder.embed_query("beta")
    assert a != b
