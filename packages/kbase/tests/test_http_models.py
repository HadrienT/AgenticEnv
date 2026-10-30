from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from corelib.errors import ConfigError, DependencyError
from kbase.config import EmbeddingsConfig, RerankConfig
from kbase.embeddings.hashing import HashingEmbedder
from kbase.embeddings.http import HttpEmbedder
from kbase.retrieval.factory import build_embedder, build_reranker
from kbase.retrieval.rerank import HttpReranker, LexicalOverlapReranker


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith("/embeddings"):
            answer: Any = {
                "data": [
                    {"index": i, "embedding": [3.0, 4.0]}
                    for i in reversed(range(len(body["input"])))
                ]
            }
        else:
            scores = [0.1, 0.9]
            answer = {
                "results": [
                    {"index": i, "relevance_score": s}
                    for i, s in enumerate(scores[: len(body["documents"])])
                ]
            }
        payload = json.dumps(answer).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_: Any) -> None:
        pass


@pytest.fixture
def base_url() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


def _embedder(base_url: str, dim: int = 2, batch_size: int = 2) -> HttpEmbedder:
    return HttpEmbedder(
        base_url=base_url,
        model_name="m",
        model_version="1",
        dim=dim,
        normalize=True,
        batch_size=batch_size,
        timeout_s=5,
    )


def test_embeds_in_batches_and_normalizes(base_url: str) -> None:
    vectors = _embedder(base_url).embed_documents(["a", "b", "c"])

    assert len(vectors) == 3
    assert list(vectors[0]) == pytest.approx([0.6, 0.8])


def test_a_dimension_mismatch_is_an_error(base_url: str) -> None:
    with pytest.raises(DependencyError, match="dimensions"):
        _embedder(base_url, dim=3).embed_query("a")


def test_an_unreachable_server_is_a_dependency_error() -> None:
    with pytest.raises(DependencyError):
        _embedder("http://127.0.0.1:1/v1").embed_query("a")


def test_factory_picks_the_configured_embedder() -> None:
    config = EmbeddingsConfig(
        provider="local",
        model_name="hashing-bow",
        model_version="1",
        dim=8,
        batch_size=1,
        normalize=True,
    )

    assert isinstance(build_embedder(config), HashingEmbedder)
    assert isinstance(
        build_embedder(config.model_copy(update={"provider": "http", "base_url": "http://x"})),
        HttpEmbedder,
    )
    with pytest.raises(ConfigError):
        build_embedder(config.model_copy(update={"provider": "http"}))


def test_factory_picks_the_configured_reranker() -> None:
    config = RerankConfig(provider="none", model_name="m", top_k=8, candidates=50)

    assert build_reranker(config) is None
    assert isinstance(
        build_reranker(config.model_copy(update={"provider": "lexical"})), LexicalOverlapReranker
    )
    assert isinstance(
        build_reranker(config.model_copy(update={"provider": "http", "base_url": "http://x"})),
        HttpReranker,
    )
