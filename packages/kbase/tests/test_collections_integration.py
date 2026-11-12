"""Integration (WP20): a regulatory chapter and a quant note in separate collections,
searched by collection, cited by paragraph id, listed paragraph by paragraph."""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest
from corelib.db import apply_migrations, session_scope
from corelib.errors import NotFoundError
from kbase.embeddings.hashing import HashingEmbedder
from kbase.ingestion import ops
from kbase.ingestion.chunking import SectionChunker
from kbase.ingestion.parsers.markdown import MarkdownParser
from kbase.ingestion.pipeline import ingest
from kbase.lookup import list_paragraphs, list_topics
from kbase.retrieval.hybrid import HybridRetriever
from kbase.retrieval.query import RetrievalFilters, RetrievalQuery
from kbase.schemas import ChunkPolicy, IngestionRequest

pytestmark = pytest.mark.integration

_CHAPTER = """# MAR21 Standardised approach: sensitivities-based method

## Process to calculate the capital requirement

### MAR21.3

The capital requirement under the sensitivities-based method aggregates delta, vega and
curvature capital requirements across risk classes.

### MAR21.4

For each risk class, a bank must determine its instruments' sensitivity to a set of
prescribed risk factors, risk weight those sensitivities, and aggregate the resulting
risk-weighted sensitivities separately for delta and vega risk.

### MAR21.40

Vega risk weights for each risk class are set out in the tables below.
"""

_NOTE = """# Credit valuation adjustment

## 1 Exposure simulation

Credit valuation adjustment pricing simulates the exposure of a netting set with Monte
Carlo, then integrates it against the counterparty default probabilities.
"""


@pytest.fixture(autouse=True)
def _migrated() -> None:
    apply_migrations()


@pytest.fixture()
def corpus(tmp_path: Path) -> dict[str, str]:
    tag = uuid.uuid4().hex[:8]
    keys = {"regulation": f"itest-bcbs-mar21-{tag}", "quant": f"itest-cva-note-{tag}"}
    (tmp_path / "mar21.md").write_text(_CHAPTER + f"\n<!-- {tag} -->\n")
    (tmp_path / "note.md").write_text(_NOTE + f"\n<!-- {tag} -->\n")
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "collection: regulation\n"
        "documents:\n"
        f"  - {{doc_key: {keys['regulation']}, path: mar21.md, title: MAR21, "
        "doc_type: standard, topic: reg-frtb-sa, valid_from: 2023-01-01}\n"
        f"  - {{doc_key: {keys['quant']}, path: note.md, title: CVA note, doc_type: notes, "
        "topic: cva-xva, collection: quant}\n"
    )
    report = ingest(
        IngestionRequest(source="manifest", target=str(manifest), force_reparse=True),
        documents_dir=tmp_path,
        parsers=[MarkdownParser()],
        chunker=SectionChunker(),
        embedder=HashingEmbedder(dim=1024),
        policy=ChunkPolicy(
            strategy="section", target_tokens=40, max_tokens=200, min_tokens=10, overlap_tokens=0
        ),
        max_file_size_bytes=1_000_000,
        parse_timeout_s=10,
        require_page=False,
        require_section=True,
    )
    assert report.status == "success", report.errors
    yield keys  # type: ignore[misc]
    with session_scope() as session:
        ops.delete_documents(session, list(keys.values()))


def _retriever() -> HybridRetriever:
    return HybridRetriever(
        embedder=HashingEmbedder(dim=1024), reranker=None, candidates_vector=50,
        candidates_lexical=50, rrf_k=60, fts_config="simple", min_score=0.0, rerank_top_k=50,
        require_page=False, require_section=True, lexical_fallback=True,
    )  # fmt: skip


def _search(text: str, collections: list[str], strategy: str = "lexical") -> list[str]:
    result = _retriever().retrieve(
        RetrievalQuery(
            text=text,
            k=10,
            strategy=strategy,  # type: ignore[arg-type]
            rerank=False,
            filters=RetrievalFilters(collections=collections),  # type: ignore[arg-type]
        )
    )
    return [c.citation.doc_key for c in result.chunks]


def test_collections_keep_the_corpora_apart(corpus: dict[str, str]) -> None:
    # "credit valuation adjustment" exists in both: each collection only sees its own.
    assert corpus["quant"] not in _search("credit valuation adjustment exposure", ["regulation"])
    assert corpus["regulation"] not in _search("risk weight sensitivities", ["quant"])
    both = _search("risk weight sensitivities exposure", ["quant", "regulation"])
    assert corpus["regulation"] in both
    assert corpus["regulation"] not in _search("risk weight", ["quant"], strategy="vector")


def test_a_spelled_out_paragraph_finds_its_chunk_with_the_id_in_the_citation(
    corpus: dict[str, str],
) -> None:
    result = _retriever().retrieve(
        RetrievalQuery(
            text="paragraph 21.4 of MAR",
            k=5,
            strategy="lexical",
            rerank=False,
            filters=RetrievalFilters(collections=["regulation"], valid_at=date(2026, 1, 1)),
        )
    )
    top = result.chunks[0].citation
    assert top.doc_key == corpus["regulation"]
    assert "MAR21.4" in top.paragraph_ids
    assert top.collection == "regulation" and top.valid_from == date(2023, 1, 1)
    # Before it came into force, the text is not returned.
    early = _retriever().retrieve(
        RetrievalQuery(
            text="MAR21.4",
            k=5,
            strategy="lexical",
            rerank=False,
            filters=RetrievalFilters(collections=["regulation"], valid_at=date(2020, 1, 1)),
        )
    )
    assert corpus["regulation"] not in [c.citation.doc_key for c in early.chunks]


def test_list_paragraphs_returns_every_id_in_order_and_the_matching_text(
    corpus: dict[str, str],
) -> None:
    with session_scope() as session:
        listing = list_paragraphs(session, doc_key=corpus["regulation"])
        assert [p.paragraph_id for p in listing.paragraphs] == ["MAR21.3", "MAR21.4", "MAR21.40"]
        assert listing.collection == "regulation" and listing.valid_from == date(2023, 1, 1)
        assert listing.paragraphs[1].first_line.startswith("For each risk class")
        assert "Process to calculate" in listing.paragraphs[1].section_path

        one = list_paragraphs(session, doc_key=corpus["regulation"], prefix="MAR21.4")
        assert one.texts and all("MAR21.4" in t.paragraph_ids for t in one.texts)
        assert not any("Vega risk weights" in t.content for t in one.texts)

        with pytest.raises(NotFoundError):
            list_paragraphs(session, doc_key=corpus["regulation"], prefix="MAR99.1")


def test_list_topics_groups_by_collection(corpus: dict[str, str]) -> None:
    with session_scope() as session:
        summary = list_topics(session, descriptions={"regulation": "BCBS", "quant": "pricing"})
    assert summary.collections["regulation"].topics.get("reg-frtb-sa", 0) >= 1
    assert summary.collections["regulation"].description == "BCBS"
    assert "reg-frtb-sa" not in summary.collections["quant"].topics
