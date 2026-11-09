from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from kbase.retrieval.hybrid import HybridRetriever
from kbase.retrieval.rerank import reranker_text


def _hit(doc: str, i: int) -> Any:
    return SimpleNamespace(citation=SimpleNamespace(doc_key=doc), rank=i, name=f"{doc}{i}")


def _retriever(cap: int | None) -> HybridRetriever:
    return HybridRetriever(
        embedder=None, reranker=None, candidates_vector=1, candidates_lexical=1, rrf_k=60,
        fts_config="simple", min_score=0.0, rerank_top_k=1, require_page=False,
        require_section=False, max_chunks_per_document=cap,
    )  # type: ignore[arg-type]  # fmt: skip


def test_cap_per_document_then_backfill() -> None:
    ranked = [_hit("hull", 1), _hit("hull", 2), _hit("hull", 3), _hit("glass", 4)]
    kept = _retriever(2)._diversify(ranked, 3)  # noqa: SLF001
    assert [h.name for h in kept] == ["hull1", "hull2", "glass4"]
    assert [h.rank for h in kept] == [1, 2, 3]
    # Too few other documents: the capped chunks come back to fill k.
    assert [h.name for h in _retriever(1)._diversify(ranked, 3)] == ["hull1", "glass4", "hull2"]  # noqa: SLF001


def test_no_cap_keeps_the_ranking() -> None:
    ranked = [_hit("hull", 1), _hit("hull", 2)]
    assert [h.name for h in _retriever(None)._diversify(ranked, 1)] == ["hull1"]  # noqa: SLF001


def test_reranker_reads_document_and_section() -> None:
    candidate: Any = SimpleNamespace(
        citation=SimpleNamespace(document="Glasserman", section_path="2 Random › 2.3 Normals"),
        chunk=SimpleNamespace(content="body"),
    )
    assert reranker_text(candidate) == "Glasserman\n2 Random › 2.3 Normals\n\nbody"
