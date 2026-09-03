from __future__ import annotations

import pytest
from corelib.errors import ValidationError
from kbase.provenance import assert_complete, build_citation, format_citation
from kbase.schemas import Chunk, DocumentMeta


def _chunk(**overrides: object) -> Chunk:
    defaults: dict[str, object] = dict(
        chunk_id="c1",
        document_version_id="dv1",
        section_id="1",
        ordinal=0,
        kind="text",
        content="hello",
        n_tokens=1,
        page_start=1,
        page_end=1,
        has_equations=False,
        valid_from=None,
        valid_until=None,
        sha256="deadbeef",
    )
    defaults.update(overrides)
    return Chunk(**defaults)


def test_build_citation_round_trips_document_metadata() -> None:
    meta = DocumentMeta(doc_key="k", title="My Doc", doc_type="notes")
    citation = build_citation(_chunk(), meta, source_url="https://example.com")
    assert citation.document == "My Doc"
    assert citation.section == "1"
    assert citation.page == 1
    assert citation.source_url == "https://example.com"


def test_assert_complete_passes_when_required_fields_present() -> None:
    meta = DocumentMeta(doc_key="k", title="My Doc", doc_type="notes")
    citation = build_citation(_chunk(), meta)
    assert_complete(citation, require_page=True, require_section=True)


def test_assert_complete_raises_when_section_missing() -> None:
    meta = DocumentMeta(doc_key="k", title="My Doc", doc_type="notes")
    citation = build_citation(_chunk(section_id=None), meta)
    with pytest.raises(ValidationError):
        assert_complete(citation, require_page=False, require_section=True)


def test_assert_complete_raises_when_page_missing() -> None:
    meta = DocumentMeta(doc_key="k", title="My Doc", doc_type="notes")
    citation = build_citation(_chunk(page_start=None), meta)
    with pytest.raises(ValidationError):
        assert_complete(citation, require_page=True, require_section=False)


def test_format_citation_short_and_full() -> None:
    meta = DocumentMeta(doc_key="k", title="My Doc", doc_type="notes")
    citation = build_citation(_chunk(), meta)
    short = format_citation(citation, style="short")
    full = format_citation(citation, style="full")
    assert "My Doc" not in short
    assert "My Doc" in full
