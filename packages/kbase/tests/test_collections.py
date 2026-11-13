"""WP20: collections, regulatory paragraph ids, iterative HNSW scan."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from corelib.errors import ValidationError
from kbase.config import KbaseConfig, load_kbase_config
from kbase.evaluation import ReferenceQuery, _score
from kbase.harvest.manifest import append_entries
from kbase.ingestion import sources
from kbase.ingestion.chunking import SectionChunker
from kbase.regulatory import matches_prefix, normalize_paragraph_refs, paragraph_id
from kbase.retrieval.filters import to_sql_predicate
from kbase.retrieval.hybrid import HybridRetriever
from kbase.retrieval.query import RetrievalFilters
from kbase.schemas import ChunkPolicy, ContentBlock, DocumentMeta, ParsedDocument, Section
from pydantic import ValidationError as PydanticValidationError


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("MAR21.4", "MAR21.4"),
        ("CRE52.12a", "CRE52.12a"),
        ("Article 325c", "Article 325c"),
        ("Article 92 Own funds requirements", "Article 92"),
        ("MAR21 Standardised approach", None),  # a chapter, not a paragraph
        ("2.1 Bias", None),
        ("MARGIN rules", None),
    ],
)
def test_paragraph_id_reads_basel_and_eu_numbering(title: str, expected: str | None) -> None:
    assert paragraph_id(title) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("paragraph 21.4 of MAR", "MAR21.4"),
        ("what does MAR 21.4 say", "what does MAR21.4 say"),
        ("see para. 52.12 in the CRE", "see CRE52.12"),
        ("MAR21.4 and CRE 52.12", "MAR21.4 and CRE52.12"),
        ("Heston calibration 2.5 of the book", "Heston calibration 2.5 of the book"),
    ],
)
def test_spelled_out_references_become_the_indexed_token(query: str, expected: str) -> None:
    assert normalize_paragraph_refs(query) == expected


def test_prefix_covers_a_chapter_or_one_paragraph_not_its_neighbours() -> None:
    assert matches_prefix("MAR21.4", "MAR21")
    assert matches_prefix("MAR21.4", "MAR21.4") and matches_prefix("MAR21.4a", "MAR21.4")
    assert not matches_prefix("MAR21.40", "MAR21.4")
    assert not matches_prefix("MAR210.1", "MAR21")


def test_collections_filter_binds_a_parameter() -> None:
    sql, params = to_sql_predicate(RetrievalFilters(collections=["regulation"]))
    assert "d.collection = ANY(:collections)" in sql
    assert params["collections"] == ["regulation"]


def test_unknown_collection_in_config_is_rejected() -> None:
    raw = load_kbase_config().model_dump()
    raw["collections"] = {"astrology": {"description": "no"}}
    with pytest.raises(PydanticValidationError):
        KbaseConfig.model_validate(raw)


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_manifest_without_collection_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# A\n")
    manifest = _write(
        tmp_path / "m.yaml", "documents:\n  - {doc_key: a, path: a.md, title: A, doc_type: notes}\n"
    )
    with pytest.raises(ValidationError, match="no collection"):
        sources.resolve(manifest, tmp_path)


def test_manifest_default_collection_and_entry_override(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# A\n")
    manifest = _write(
        tmp_path / "m.yaml",
        "collection: regulation\njurisdiction: intl\ndocuments:\n"
        "  - {doc_key: a, path: a.md, title: A, doc_type: standard}\n"
        "  - {doc_key: b, path: a.md, title: B, doc_type: notes, collection: quant}\n",
    )
    items = sources.resolve(manifest, tmp_path)
    assert [i.meta.collection for i in items] == ["regulation", "quant"]


def test_harvest_keeps_the_manifest_collection(tmp_path: Path) -> None:
    manifest = _write(tmp_path / "m.yaml", "collection: regulation\ndocuments: []\n")
    append_entries(manifest, [{"doc_key": "x", "path": "x.md"}])
    assert yaml.safe_load(manifest.read_text())["collection"] == "regulation"
    fresh = tmp_path / "fresh.yaml"
    append_entries(fresh, [{"doc_key": "x", "path": "x.md"}])
    assert yaml.safe_load(fresh.read_text())["collection"] == "quant"


def _section(sid: str, parent: str | None, level: int, title: str) -> Section:
    return Section(section_id=sid, parent_id=parent, level=level, ordinal=1, title=title, path=sid)


def test_chunks_carry_the_paragraph_ids_of_their_sections() -> None:
    sections = [
        _section("0", None, 1, "MAR21 Standardised approach"),
        _section("h", "0", 2, "Process to calculate the capital requirement"),
        _section("p3", "h", 3, "MAR21.3"),
        _section("p4", "h", 3, "MAR21.4"),
        _section("p5", "h", 3, "MAR21.5"),
    ]
    long_text = " ".join(["The bank must determine sensitivities for each risk factor."] * 30)
    blocks = [
        ContentBlock(kind="text", text="Short paragraph three.", section_id="p3"),
        ContentBlock(kind="text", text="Short paragraph four.", section_id="p4"),
        ContentBlock(kind="text", text=long_text, section_id="p5"),
    ]
    doc = ParsedDocument(
        meta=DocumentMeta(doc_key="bcbs-mar21", title="MAR21", doc_type="standard"),
        version="1", sha256="x", page_count=None, sections=sections, blocks=blocks,
        parser_name="m", parser_version="2",
    )  # fmt: skip
    policy = ChunkPolicy(
        strategy="section", target_tokens=100, max_tokens=200, min_tokens=40, overlap_tokens=10
    )
    chunks = SectionChunker().chunk(doc, policy)
    # Short paragraphs merge with the start of the next one; the long paragraph is split
    # and every part keeps its id.
    assert chunks[0].paragraph_ids == ["MAR21.3", "MAR21.4", "MAR21.5"]
    assert len(chunks) > 2 and all(c.paragraph_ids == ["MAR21.5"] for c in chunks[1:])


def _eval_chunk(doc_key: str, paragraphs: list[str]) -> Any:
    return SimpleNamespace(
        citation=SimpleNamespace(doc_key=doc_key, section_path="", paragraph_ids=paragraphs),
        chunk=SimpleNamespace(content=""),
    )


def test_expected_paragraphs_match_exactly() -> None:
    query = ReferenceQuery(
        category="exact-id", text="t", expected=["bcbs-mar21"], expected_paragraphs=["MAR21.4"]
    )
    chunks = [_eval_chunk("bcbs-mar21", ["MAR21.40"]), _eval_chunk("bcbs-mar21", ["MAR21.4"])]
    assert _score(query, chunks, 1.0).section_hit_rank == 2


class _FakeSession:
    def __init__(self, version: str | None) -> None:
        self.version = version
        self.statements: list[str] = []

    def execute(self, statement: Any, *_args: Any) -> Any:
        sql = str(statement)
        self.statements.append(sql)
        return SimpleNamespace(scalar_one_or_none=lambda: self.version)


def _retriever(**kwargs: Any) -> HybridRetriever:
    return HybridRetriever(
        embedder=SimpleNamespace(),  # type: ignore[arg-type]
        reranker=None, candidates_vector=10, candidates_lexical=10, rrf_k=60,
        fts_config="simple", min_score=0.0, rerank_top_k=10, require_page=False,
        require_section=False, **kwargs,
    )  # fmt: skip


def test_iterative_scan_is_set_on_pgvector_08() -> None:
    retriever = _retriever(hnsw_iterative_scan="relaxed_order", hnsw_max_scan_tuples=5000)
    session = _FakeSession("0.8.1")
    assert retriever._enable_iterative_scan(session) is None  # type: ignore[arg-type]
    assert "SET LOCAL hnsw.iterative_scan = relaxed_order" in session.statements
    assert "SET LOCAL hnsw.max_scan_tuples = 5000" in session.statements


def test_iterative_scan_on_old_pgvector_warns_and_sets_nothing() -> None:
    retriever = _retriever(hnsw_iterative_scan="relaxed_order")
    session = _FakeSession("0.7.4")
    warning = retriever._enable_iterative_scan(session)  # type: ignore[arg-type]
    assert warning is not None and "pgvector < 0.8" in warning
    assert not any(s.startswith("SET") for s in session.statements)
    # Probed once per retriever.
    retriever._enable_iterative_scan(session)  # type: ignore[arg-type]
    assert sum("pg_extension" in s for s in session.statements) == 1


def test_iterative_scan_off_does_nothing() -> None:
    session = _FakeSession("0.8.1")
    assert _retriever()._enable_iterative_scan(session) is None  # type: ignore[arg-type]
    assert session.statements == []


def test_paragraph_tokens_are_kept_for_the_any_term_fallback() -> None:
    from kbase.regulatory import paragraph_tokens

    assert paragraph_tokens("What does MAR33.3 require, and cre52.1?") == ["mar33.3", "cre52.1"]
    assert paragraph_tokens("Heston 2.1 calibration") == []
