from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from corelib.db import apply_migrations
from kbase.embeddings.hashing import HashingEmbedder
from kbase.ingestion.chunking import StructuralChunker
from kbase.ingestion.parsers.markdown import MarkdownParser
from kbase.ingestion.pipeline import ingest
from kbase.schemas import ChunkPolicy, IngestionRequest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "corpus"


@pytest.fixture
def documents_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def manifest_path() -> Path:
    return FIXTURES_DIR / "manifest.yaml"


@pytest.fixture
def golden_corpus() -> None:
    """Ingests the fixed WP05 golden corpus (`fixtures/corpus/manifest.yaml`).

    Content-addressed dedup (WP04) makes this idempotent: safe to call from every
    retrieval integration test without cross-test pollution or duplicate rows.
    """
    apply_migrations()
    ingest(
        IngestionRequest(source="manifest", target=str(FIXTURES_DIR / "manifest.yaml")),
        documents_dir=FIXTURES_DIR,
        parsers=[MarkdownParser()],
        chunker=StructuralChunker(),
        embedder=HashingEmbedder(dim=1024),
        policy=ChunkPolicy(target_tokens=50, max_tokens=100, overlap_tokens=10),
        max_file_size_bytes=1_000_000,
        parse_timeout_s=10,
        require_page=False,
        require_section=True,
    )


@pytest.fixture
def unique_source_relpath() -> Iterator[str]:
    """Writes a throwaway markdown file with unique content under `documents_dir/raw/`
    so each test gets its own sha256 (dedup is content-addressed, not per-test-scoped)."""
    relpath = f"raw/tmp-{uuid.uuid4().hex}.md"
    path = FIXTURES_DIR / relpath
    path.write_text(f"<!-- page:1 -->\n# Heading\n\nUnique content nonce {uuid.uuid4().hex}.\n")
    try:
        yield relpath
    finally:
        path.unlink(missing_ok=True)
