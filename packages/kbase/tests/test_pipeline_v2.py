"""Integration: section chunking, curation, contextual embeddings, version replacement
and deletion (WP19)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from corelib.db import apply_migrations, session_scope
from kbase.embeddings.hashing import HashingEmbedder
from kbase.ingestion import ops
from kbase.ingestion.chunking import SectionChunker
from kbase.ingestion.parsers.markdown import MarkdownParser
from kbase.ingestion.pipeline import ingest
from kbase.schemas import ChunkPolicy, IngestionRequest
from sqlalchemy import text

pytestmark = pytest.mark.integration

_BOOK = """# A Book

## Contents

1 Monte Carlo ........ 3

## 1.1 Normal variables

Two uniforms give two normals with the Box-Muller method:

$$
Z = \\sqrt{-2 \\ln U_1} \\cos(2 \\pi U_2)
$$ (2.24)

which are independent standard normals.

## 1.2 Exercises

Prove it.
"""


class _RecordingEmbedder(HashingEmbedder):
    def __init__(self) -> None:
        super().__init__(dim=1024)
        self.inputs: list[str] = []

    def embed_documents(self, texts):  # type: ignore[no-untyped-def]
        self.inputs.extend(texts)
        return super().embed_documents(texts)


def _run(tmp_path: Path, doc_key: str, body: str, embedder: HashingEmbedder) -> object:
    # `document_versions.sha256` is unique across documents: make each file distinct.
    (tmp_path / "book.md").write_text(body + f"\n<!-- {doc_key} -->\n")
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        f"documents:\n  - doc_key: {doc_key}\n    path: book.md\n    title: A Book\n"
        "    doc_type: book\n"
    )
    return ingest(
        IngestionRequest(source="manifest", target=str(manifest), force_reparse=True),
        documents_dir=tmp_path,
        parsers=[MarkdownParser()],
        chunker=SectionChunker(),
        embedder=embedder,
        policy=ChunkPolicy(
            strategy="section", target_tokens=300, max_tokens=500, min_tokens=50, overlap_tokens=20
        ),
        max_file_size_bytes=1_000_000,
        parse_timeout_s=10,
        require_page=False,
        require_section=True,
        drop_section_patterns=["(table of )?contents", "exercises?"],
        contextual_embeddings=True,
    )


@pytest.fixture(autouse=True)
def _migrated() -> None:
    apply_migrations()


def _count(sql: str, key: str) -> int:
    with session_scope() as session:
        return int(session.execute(text(sql), {"k": key}).scalar_one())


def test_section_chunks_keep_equations_inline_and_drop_curated_sections(tmp_path: Path) -> None:
    key = f"itest-v2-{uuid.uuid4().hex[:8]}"
    embedder = _RecordingEmbedder()
    report = _run(tmp_path, key, _BOOK, embedder)
    assert report.status == "success"  # type: ignore[attr-defined]

    with session_scope() as session:
        chunks = session.execute(
            text(
                "SELECT c.kind, c.content FROM kb.chunks c "
                "JOIN kb.document_versions dv ON dv.id = c.document_version_id "
                "JOIN kb.documents d ON d.id = dv.document_id WHERE d.doc_key = :k"
            ),
            {"k": key},
        ).all()
        number = session.execute(
            text(
                "SELECT e.equation_number FROM kb.equations e "
                "JOIN kb.document_versions dv ON dv.id = e.document_version_id "
                "JOIN kb.documents d ON d.id = dv.document_id WHERE d.doc_key = :k"
            ),
            {"k": key},
        ).scalar_one()
    contents = "\n".join(c.content for c in chunks)
    assert {c.kind for c in chunks} == {"text"}
    assert "Box-Muller method:\n\n$$ Z = " in contents and "$$ (2.24)" in contents
    assert "Prove it" not in contents and "Monte Carlo ...." not in contents
    assert number == "2.24"
    with session_scope() as session:
        report = ops.verify(
            session, expected_dim=1024, model_name="hashing-bow", model_version="1",
            require_section=True,
        )  # fmt: skip
    assert report.equations_orphaned == 0  # inline equations are not orphans
    assert any(i.startswith("A Book\n1.1 Normal variables\n\n") for i in embedder.inputs)


def test_reingestion_replaces_the_previous_version_and_delete_removes_all(
    tmp_path: Path,
) -> None:
    key = f"itest-v2-{uuid.uuid4().hex[:8]}"
    _run(tmp_path, key, _BOOK, HashingEmbedder(dim=1024))
    _run(
        tmp_path,
        key,
        _BOOK.replace("independent", "independent, exactly"),
        HashingEmbedder(dim=1024),
    )

    versions = "SELECT count(*) FROM kb.document_versions dv JOIN kb.documents d ON d.id = dv.document_id WHERE d.doc_key = :k"  # noqa: E501
    chunks = "SELECT count(*) FROM kb.chunks c JOIN kb.document_versions dv ON dv.id = c.document_version_id JOIN kb.documents d ON d.id = dv.document_id WHERE d.doc_key = :k"  # noqa: E501
    assert _count(versions, key) == 1
    with session_scope() as session:
        assert ops.delete_documents(session, [key, "no-such-doc"]) == [key]
    assert _count(versions, key) == 0 and _count(chunks, key) == 0
