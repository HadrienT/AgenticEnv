from __future__ import annotations

import pytest
from corelib.db import apply_migrations, session_scope
from kbase.retrieval import lexical, store
from kbase.retrieval.filters import to_sql_predicate
from kbase.retrieval.query import RetrievalFilters

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _migrated() -> None:
    apply_migrations()


def test_lexical_search_returns_candidates_sorted_by_descending_rank(golden_corpus: None) -> None:
    with session_scope() as session:
        hits = lexical.search(
            session,
            query_text="volatility",
            fts_config="simple",
            predicate_sql="",
            predicate_params={},
            candidates_n=10,
        )

    assert hits
    ranks = [h.score for h in hits]
    assert ranks == sorted(ranks, reverse=True)


def test_lexical_search_finds_word_unique_to_one_document(golden_corpus: None) -> None:
    """ "estimator" only appears in `sample-paper` -> every hit must be a research_paper."""
    with session_scope() as session:
        hits = lexical.search(
            session,
            query_text="estimator",
            fts_config="simple",
            predicate_sql="",
            predicate_params={},
            candidates_n=10,
        )
        assert hits
        candidates = store.load_candidates(session, [h.chunk_id for h in hits])

    assert all(meta.doc_type == "research_paper" for _, meta in candidates.values())


def test_lexical_search_with_no_match_returns_empty_without_error(golden_corpus: None) -> None:
    with session_scope() as session:
        hits = lexical.search(
            session,
            query_text="xyznonexistenttoken",
            fts_config="simple",
            predicate_sql="",
            predicate_params={},
            candidates_n=10,
        )
    assert hits == []


def test_lexical_search_respects_topic_filter(golden_corpus: None) -> None:
    predicate_sql, predicate_params = to_sql_predicate(RetrievalFilters(topics=["risk"]))
    with session_scope() as session:
        hits = lexical.search(
            session,
            query_text="volatility",
            fts_config="simple",
            predicate_sql=predicate_sql,
            predicate_params=predicate_params,
            candidates_n=50,
        )
        assert hits
        candidates = store.load_candidates(session, [h.chunk_id for h in hits])

    assert all(meta.topic == "risk" for _, meta in candidates.values())
