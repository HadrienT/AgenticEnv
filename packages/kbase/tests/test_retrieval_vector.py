from __future__ import annotations

import pytest
from corelib.db import apply_migrations, session_scope
from kbase.embeddings.hashing import HashingEmbedder
from kbase.retrieval import store, vector
from kbase.retrieval.filters import to_sql_predicate
from kbase.retrieval.query import RetrievalFilters
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _migrated() -> None:
    apply_migrations()


def test_vector_search_returns_candidates_sorted_by_ascending_distance(
    golden_corpus: None,
) -> None:
    embedder = HashingEmbedder(dim=1024)
    embedding = embedder.embed_query("volatility model estimator dispersion of returns")

    with session_scope() as session:
        hits = vector.search(
            session,
            embedding=embedding,
            model_name=embedder.model_name,
            model_version=embedder.model_version,
            predicate_sql="",
            predicate_params={},
            candidates_n=10,
        )

    assert hits
    distances = [h.score for h in hits]
    assert distances == sorted(distances)


def test_vector_search_respects_doc_type_filter(golden_corpus: None) -> None:
    embedder = HashingEmbedder(dim=1024)
    embedding = embedder.embed_query("volatility")
    predicate_sql, predicate_params = to_sql_predicate(
        RetrievalFilters(doc_types=["research_paper"])
    )

    with session_scope() as session:
        hits = vector.search(
            session,
            embedding=embedding,
            model_name=embedder.model_name,
            model_version=embedder.model_version,
            predicate_sql=predicate_sql,
            predicate_params=predicate_params,
            candidates_n=50,
        )
        assert hits
        candidates = store.load_candidates(session, [h.chunk_id for h in hits])

    assert all(meta.doc_type == "research_paper" for _, meta in candidates.values())


def test_vector_search_dimension_mismatch_is_rejected_by_postgres(golden_corpus: None) -> None:
    with session_scope() as session, pytest.raises(DBAPIError):
        vector.search(
            session,
            embedding=[0.1, 0.2],
            model_name="hashing-bow",
            model_version="1",
            predicate_sql="",
            predicate_params={},
            candidates_n=10,
        )
