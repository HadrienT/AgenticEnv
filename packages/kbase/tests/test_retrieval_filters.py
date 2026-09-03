from __future__ import annotations

from kbase.retrieval.filters import to_sql_predicate
from kbase.retrieval.query import RetrievalFilters


def test_empty_filters_produce_no_predicate() -> None:
    sql, params = to_sql_predicate(RetrievalFilters())
    assert sql == ""
    assert params == {}


def test_each_filter_field_binds_a_named_parameter() -> None:
    filters = RetrievalFilters(
        doc_types=["notes"],
        topics=["risk"],
        asset_classes=["equities"],
        doc_keys=["sample-notes"],
        year_min=2020,
        year_max=2025,
        has_equations=True,
    )
    sql, params = to_sql_predicate(filters)
    assert "d.doc_type = ANY(:doc_types)" in sql
    assert "d.topic = ANY(:topics)" in sql
    assert "d.asset_class = ANY(:asset_classes)" in sql
    assert "d.doc_key = ANY(:doc_keys)" in sql
    assert "d.year >= :year_min" in sql
    assert "d.year <= :year_max" in sql
    assert "c.has_equations = :has_equations" in sql
    assert params == {
        "doc_types": ["notes"],
        "topics": ["risk"],
        "asset_classes": ["equities"],
        "doc_keys": ["sample-notes"],
        "year_min": 2020,
        "year_max": 2025,
        "has_equations": True,
    }


def test_valid_at_produces_both_bounds() -> None:
    from datetime import date

    sql, params = to_sql_predicate(RetrievalFilters(valid_at=date(2024, 6, 1)))
    assert "c.valid_from IS NULL OR c.valid_from <= :valid_at" in sql
    assert "c.valid_until IS NULL OR c.valid_until >= :valid_at" in sql
    assert params == {"valid_at": date(2024, 6, 1)}


def test_sql_injection_attempt_is_bound_as_a_value_not_concatenated() -> None:
    """A malicious string in a filter field must never be spliced into the SQL text —
    it can only ever end up as a *value* inside a bound array parameter."""
    payload = "notes'; DROP TABLE kb.chunks; --"
    sql, params = to_sql_predicate(RetrievalFilters(doc_types=[payload]))
    assert payload not in sql
    assert params["doc_types"] == [payload]
