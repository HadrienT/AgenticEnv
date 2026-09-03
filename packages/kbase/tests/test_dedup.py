from __future__ import annotations

import uuid

import pytest
from corelib.db import apply_migrations, session_scope
from kbase.ingestion.dedup import already_ingested
from sqlalchemy import text

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _migrated() -> None:
    apply_migrations()


def test_already_ingested_returns_none_for_unknown_sha256() -> None:
    with session_scope() as session:
        assert already_ingested(session, "0" * 64) is None


def test_already_ingested_finds_existing_document_version() -> None:
    doc_key = f"dedup-test-doc-{uuid.uuid4().hex[:8]}"
    sha256 = f"dedupsha256-{uuid.uuid4().hex}"
    with session_scope() as session:
        doc_id = session.execute(
            text(
                "INSERT INTO kb.documents (id, doc_key, title, doc_type) "
                "VALUES (gen_random_uuid(), :doc_key, 'T', 'notes') RETURNING id"
            ),
            {"doc_key": doc_key},
        ).scalar_one()
        dv_id = session.execute(
            text(
                "INSERT INTO kb.document_versions "
                "(id, document_id, version, file_path, sha256, ingestion_date, "
                " parser_name, parser_version, status) "
                "VALUES (gen_random_uuid(), :document_id, '1', '/tmp/x.md', "
                " :sha256, now(), 'markdown', '1', 'indexed') RETURNING id"
            ),
            {"document_id": doc_id, "sha256": sha256},
        ).scalar_one()

    with session_scope() as session:
        found = already_ingested(session, sha256)
    assert found is not None
    assert str(found) == str(dv_id)
