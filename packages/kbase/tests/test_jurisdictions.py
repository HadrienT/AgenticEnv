"""WP21: jurisdictions of regulatory documents, document types, not-expired default."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from corelib.errors import ValidationError
from kbase.config import KbaseConfig, load_kbase_config
from kbase.ingestion import sources
from kbase.provenance import format_citation
from kbase.regulatory import (
    matches_prefix,
    normalize_paragraph_refs,
    paragraph_id,
    paragraph_tokens,
)
from kbase.retrieval.filters import to_sql_predicate
from kbase.retrieval.query import RetrievalFilters
from kbase.schemas import Citation
from pydantic import ValidationError as PydanticValidationError


def test_jurisdiction_filter_only_restricts_regulatory_documents() -> None:
    sql, params = to_sql_predicate(RetrievalFilters(jurisdictions=["eu", "intl"]))
    assert "(d.collection <> 'regulation' OR d.jurisdiction = ANY(:jurisdictions))" in sql
    assert params["jurisdictions"] == ["eu", "intl"]


def test_not_expired_keeps_texts_that_apply_later() -> None:
    sql, params = to_sql_predicate(RetrievalFilters(not_expired_at=date(2026, 11, 13)))
    assert "(c.valid_until IS NULL OR c.valid_until >= :not_expired_at)" in sql
    assert "valid_from" not in sql
    assert params["not_expired_at"] == date(2026, 11, 13)


def test_an_explicit_date_wins_over_not_expired() -> None:
    sql, params = to_sql_predicate(
        RetrievalFilters(valid_at=date(2019, 1, 1), not_expired_at=date(2026, 11, 13))
    )
    assert ":valid_at" in sql and ":not_expired_at" not in sql
    assert "not_expired_at" not in params


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_regulatory_entry_without_jurisdiction_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# A\n")
    manifest = _write(
        tmp_path / "m.yaml",
        "collection: regulation\ndocuments:\n"
        "  - {doc_key: a, path: a.md, title: A, doc_type: law}\n",
    )
    with pytest.raises(ValidationError, match="jurisdiction"):
        sources.resolve(manifest, tmp_path)


def test_quant_entry_with_a_jurisdiction_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# A\n")
    manifest = _write(
        tmp_path / "m.yaml",
        "collection: quant\ndocuments:\n"
        "  - {doc_key: a, path: a.md, title: A, doc_type: notes, jurisdiction: eu}\n",
    )
    with pytest.raises(ValidationError, match="jurisdiction"):
        sources.resolve(manifest, tmp_path)


def test_file_default_jurisdiction_entry_override_and_quant_entries(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# A\n")
    manifest = _write(
        tmp_path / "m.yaml",
        "collection: regulation\njurisdiction: intl\ndocuments:\n"
        "  - {doc_key: a, path: a.md, title: A, doc_type: standard}\n"
        "  - {doc_key: b, path: a.md, title: B, doc_type: law, jurisdiction: uk}\n"
        "  - {doc_key: c, path: a.md, title: C, doc_type: notes, collection: quant}\n",
    )
    items = sources.resolve(manifest, tmp_path)
    assert [i.meta.jurisdiction for i in items] == ["intl", "uk", None]
    assert [i.meta.doc_type for i in items] == ["standard", "law", "notes"]


def test_unknown_jurisdiction_in_config_is_rejected() -> None:
    raw = load_kbase_config().model_dump()
    raw["jurisdictions"] = {"mars": {"description": "no"}}
    with pytest.raises(PydanticValidationError):
        KbaseConfig.model_validate(raw)


def test_full_citation_starts_with_jurisdiction_and_type() -> None:
    citation = Citation(
        document="CRR",
        authors=["European Parliament and Council"],
        year=2024,
        section="s1",
        page=None,
        equation_number=None,
        source_url=None,
        sha256="x",
        doc_key="eu-crr-p3-t2-c6",
        ingested_at=datetime(2026, 11, 13, tzinfo=UTC),
        paragraph_ids=["Article 274(2)"],
        collection="regulation",
        jurisdiction="eu",
        doc_type="law",
    )
    text = format_citation(citation, "full")
    assert text.startswith("[EU, law] European Parliament and Council et al. (2024). CRR.")
    assert "Article 274(2)." in text


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Article 274(2)", "Article 274(2)"),
        ("Article 325c(2) The sum of three components", "Article 325c(2)"),
        ("Article 274 Exposure value", "Article 274"),
        ("Rule 2.1", "Rule 2.1"),
        ("Rule 3.4A A firm must", "Rule 3.4A"),
        ("§ 217.132(c)(1)", "§ 217.132(c)(1)"),
        ("§ 217.132 Counterparty credit risk", "§ 217.132"),
        ("§240.18a-3(c)(1)(ii)(A)", "§ 240.18a-3(c)(1)(ii)(A)"),
        ("2.1 Bias", None),
        ("Rules of thumb", None),
    ],
)
def test_paragraph_ids_of_eu_uk_and_us_texts(title: str, expected: str | None) -> None:
    assert paragraph_id(title) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("what does Art. 274(2) CRR require", "what does Article 274(2) CRR require"),
        ("article 274 paragraph 2", "Article 274(2)"),
        ("12 CFR 217.132(c)(5) netting", "§ 217.132(c)(5) netting"),
        ("12 C.F.R. § 217.132", "§ 217.132"),
        ("see section 217.201 of Regulation Q", "see § 217.201 of Regulation Q"),
        ("Heston calibration 2.5 of the book", "Heston calibration 2.5 of the book"),
    ],
)
def test_spelled_out_eu_and_us_references_are_normalised(query: str, expected: str) -> None:
    assert normalize_paragraph_refs(query) == expected


def test_lexical_tokens_for_articles_and_cfr_sections() -> None:
    tokens = paragraph_tokens("Article 274(2), § 217.132(c) and MAR21.4")
    assert tokens == ["mar21.4", "article <-> 274", "217.132"]


def test_prefix_covers_paragraphs_of_an_article_or_cfr_section() -> None:
    assert matches_prefix("Article 274(2)", "Article 274")
    assert not matches_prefix("Article 2745", "Article 274")
    assert matches_prefix("§ 217.132(c)(1)", "§ 217.132(c)")
    assert matches_prefix("§ 217.132(c)(1)", "§ 217.132")
    assert not matches_prefix("§ 217.1320", "§ 217.132")
