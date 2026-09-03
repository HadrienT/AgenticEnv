from __future__ import annotations

import pytest
from corelib.db import session_scope
from corelib.errors import NotFoundError, ValidationError
from kbase.lookup import get_document, get_equation, list_topics

pytestmark = pytest.mark.integration


def test_get_document_by_doc_key_returns_metadata_and_sections(golden_corpus: None) -> None:
    with session_scope() as session:
        detail = get_document(session, doc_key="sample-paper")
    assert detail.meta.doc_key == "sample-paper"
    assert detail.meta.title == "A Small Paper on Volatility"
    assert detail.sections
    assert any(s.title == "Derivation" for s in detail.sections)


def test_get_document_by_document_version_id(golden_corpus: None) -> None:
    with session_scope() as session:
        by_key = get_document(session, doc_key="sample-paper")
        by_version = get_document(session, document_version_id=by_key.document_version_id)
    assert by_version.meta.doc_key == "sample-paper"


def test_get_document_unknown_doc_key_raises_not_found(golden_corpus: None) -> None:
    with session_scope() as session, pytest.raises(NotFoundError):
        get_document(session, doc_key="does-not-exist")


def test_get_document_requires_exactly_one_identifier(golden_corpus: None) -> None:
    with session_scope() as session, pytest.raises(ValidationError):
        get_document(session)
    with session_scope() as session, pytest.raises(ValidationError):
        get_document(session, doc_key="sample-paper", document_version_id="00000000")


def test_get_equation_by_doc_key_and_number(golden_corpus: None) -> None:
    with session_scope() as session:
        detail = get_equation(session, doc_key="sample-paper", equation_number="2")
    assert detail.equation.equation_number == "2"
    assert "sigma" in detail.equation.latex.lower() or "\\sigma" in detail.equation.latex
    assert detail.citation.document == "A Small Paper on Volatility"
    assert detail.citation.doc_key == "sample-paper"


def test_get_equation_by_chunk_id(golden_corpus: None) -> None:
    with session_scope() as session:
        by_number = get_equation(session, doc_key="sample-paper", equation_number="2")
        by_chunk = get_equation(session, chunk_id=by_number.chunk_id)
    assert by_chunk.equation.equation_number == "2"


def test_get_equation_chunk_id_exclusive_of_other_args(golden_corpus: None) -> None:
    with session_scope() as session, pytest.raises(ValidationError):
        get_equation(session, doc_key="sample-paper", equation_number="2", chunk_id="abc")


def test_get_equation_requires_an_identifier(golden_corpus: None) -> None:
    with session_scope() as session, pytest.raises(ValidationError):
        get_equation(session)


def test_get_equation_unknown_raises_not_found(golden_corpus: None) -> None:
    with session_scope() as session, pytest.raises(NotFoundError):
        get_equation(session, doc_key="sample-paper", equation_number="999")


def test_list_topics_reports_the_golden_corpus_coverage(golden_corpus: None) -> None:
    with session_scope() as session:
        summary = list_topics(session)
    assert "risk" in summary.topics
    assert "volatility" in summary.topics
    assert "equities" in summary.asset_classes
    assert "options" in summary.asset_classes
    assert "notes" in summary.doc_types
    assert "research_paper" in summary.doc_types
    assert summary.year_min is not None and summary.year_min <= 2023
    assert summary.year_max is not None and summary.year_max >= 2024
    assert summary.document_count >= 2
