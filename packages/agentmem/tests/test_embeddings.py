from __future__ import annotations

import math

from agentmem.embeddings import HashingEmbedder


def test_embed_is_deterministic() -> None:
    embedder = HashingEmbedder(dim=32)
    assert embedder.embed("hello world") == embedder.embed("hello world")


def test_embed_is_normalized_by_default() -> None:
    embedder = HashingEmbedder(dim=32)
    vector = embedder.embed("some episodic memory content")
    norm = math.sqrt(sum(v * v for v in vector))
    assert math.isclose(norm, 1.0, abs_tol=1e-9)


def test_embed_empty_text_returns_zero_vector() -> None:
    embedder = HashingEmbedder(dim=16)
    assert embedder.embed("") == [0.0] * 16


def test_different_texts_usually_differ() -> None:
    embedder = HashingEmbedder(dim=64)
    assert embedder.embed("alpha") != embedder.embed("beta")


def test_not_normalized_when_disabled() -> None:
    embedder = HashingEmbedder(dim=16, normalize=False)
    vector = embedder.embed("a a a")
    assert any(abs(v) > 1.0 for v in vector) or vector == [0.0] * 16
