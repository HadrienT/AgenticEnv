"""Metadata filter -> parameterized SQL (WP05 §6). No string concatenation, ever:
every clause below binds a named parameter; the "allowlist" is that
`RetrievalFilters` is a fixed pydantic schema, so there is no dynamic column name
to inject in the first place.
"""

from __future__ import annotations

from typing import Any

from kbase.retrieval.query import RetrievalFilters


def to_sql_predicate(filters: RetrievalFilters) -> tuple[str, dict[str, Any]]:
    """Returns (`"AND ..."` fragment or `""`, bound params) to splice after a base `WHERE`."""
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if filters.doc_types:
        clauses.append("d.doc_type = ANY(:doc_types)")
        params["doc_types"] = list(filters.doc_types)
    if filters.topics:
        clauses.append("d.topic = ANY(:topics)")
        params["topics"] = list(filters.topics)
    if filters.asset_classes:
        clauses.append("d.asset_class = ANY(:asset_classes)")
        params["asset_classes"] = list(filters.asset_classes)
    if filters.doc_keys:
        clauses.append("d.doc_key = ANY(:doc_keys)")
        params["doc_keys"] = list(filters.doc_keys)
    if filters.year_min is not None:
        clauses.append("d.year >= :year_min")
        params["year_min"] = filters.year_min
    if filters.year_max is not None:
        clauses.append("d.year <= :year_max")
        params["year_max"] = filters.year_max
    if filters.has_equations is not None:
        clauses.append("c.has_equations = :has_equations")
        params["has_equations"] = filters.has_equations
    if filters.valid_at is not None:
        clauses.append("(c.valid_from IS NULL OR c.valid_from <= :valid_at)")
        clauses.append("(c.valid_until IS NULL OR c.valid_until >= :valid_at)")
        params["valid_at"] = filters.valid_at

    if not clauses:
        return "", params
    return " AND " + " AND ".join(clauses), params
