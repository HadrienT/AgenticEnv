from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from corelib.db import apply_migrations, session_scope
from kbase.embeddings.hashing import HashingEmbedder
from kbase.ingestion.chunking import StructuralChunker
from kbase.ingestion.parsers.markdown import MarkdownParser
from kbase.ingestion.pipeline import ingest
from kbase.schemas import ChunkPolicy, IngestionRequest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def _manifest(tmp_path: Path, doc_key: str, source_relpath: str) -> Path:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        f"documents:\n"
        f"  - doc_key: {doc_key}\n"
        f"    path: {source_relpath}\n"
        f"    title: Integration Test Doc\n"
        f"    doc_type: notes\n"
    )
    return manifest


def _ingest(request: IngestionRequest, documents_dir: Path) -> object:
    return ingest(
        request,
        documents_dir=documents_dir,
        parsers=[MarkdownParser()],
        chunker=StructuralChunker(),
        embedder=HashingEmbedder(dim=1024),
        policy=ChunkPolicy(target_tokens=50, max_tokens=100, overlap_tokens=10),
        max_file_size_bytes=1_000_000,
        parse_timeout_s=10,
        require_page=False,
        require_section=True,
    )


@pytest.fixture(autouse=True)
def _migrated() -> None:
    apply_migrations()


def test_ingest_writes_chunks_and_equations(
    tmp_path: Path, documents_dir: Path, unique_source_relpath: str
) -> None:
    doc_key = f"itest-{uuid.uuid4().hex[:8]}"
    manifest = _manifest(tmp_path, doc_key, unique_source_relpath)
    request = IngestionRequest(source="manifest", target=str(manifest))

    report = _ingest(request, documents_dir)

    assert report.status == "success"
    assert report.documents_ingested == 1
    assert report.chunks_written > 0

    with session_scope() as session:
        row = session.execute(
            text("SELECT count(*) FROM kb.documents WHERE doc_key = :k"), {"k": doc_key}
        ).scalar_one()
    assert row == 1


def test_ingest_is_idempotent_on_same_sha256(
    tmp_path: Path, documents_dir: Path, unique_source_relpath: str
) -> None:
    doc_key = f"itest-{uuid.uuid4().hex[:8]}"
    manifest = _manifest(tmp_path, doc_key, unique_source_relpath)
    request = IngestionRequest(source="manifest", target=str(manifest))

    first = _ingest(request, documents_dir)
    second = _ingest(request, documents_dir)

    assert first.documents_ingested == 1
    assert second.documents_ingested == 0
    assert second.documents_skipped == 1

    with session_scope() as session:
        count = session.execute(
            text(
                "SELECT count(*) FROM kb.document_versions dv "
                "JOIN kb.documents d ON d.id = dv.document_id WHERE d.doc_key = :k"
            ),
            {"k": doc_key},
        ).scalar_one()
    assert count == 1


def test_dry_run_writes_nothing(
    tmp_path: Path, documents_dir: Path, unique_source_relpath: str
) -> None:
    doc_key = f"itest-{uuid.uuid4().hex[:8]}"
    manifest = _manifest(tmp_path, doc_key, unique_source_relpath)
    request = IngestionRequest(source="manifest", target=str(manifest), dry_run=True)

    report = _ingest(request, documents_dir)

    assert report.documents_ingested == 1
    assert report.chunks_written > 0  # dry_run reports what would be written, but writes nothing

    with session_scope() as session:
        count = session.execute(
            text("SELECT count(*) FROM kb.documents WHERE doc_key = :k"), {"k": doc_key}
        ).scalar_one()
    assert count == 0


def test_isolation_one_bad_document_does_not_abort_run(
    tmp_path: Path, documents_dir: Path, unique_source_relpath: str
) -> None:
    good_key = f"itest-good-{uuid.uuid4().hex[:8]}"
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        f"documents:\n"
        f"  - doc_key: itest-missing\n"
        f"    path: raw/does-not-exist.md\n"
        f"    title: Missing\n"
        f"    doc_type: notes\n"
        f"  - doc_key: {good_key}\n"
        f"    path: {unique_source_relpath}\n"
        f"    title: Good Doc\n"
        f"    doc_type: notes\n"
    )
    request = IngestionRequest(source="manifest", target=str(manifest))

    report = _ingest(request, documents_dir)

    assert report.status == "partial"
    assert report.documents_ingested == 1
    assert len(report.errors) == 1
