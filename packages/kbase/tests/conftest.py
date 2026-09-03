from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "corpus"


@pytest.fixture
def documents_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def manifest_path() -> Path:
    return FIXTURES_DIR / "manifest.yaml"


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
