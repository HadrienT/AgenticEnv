from __future__ import annotations

from kbase.schemas import ChunkPolicy, DocumentMeta


def test_document_meta_requires_doc_key_and_title() -> None:
    meta = DocumentMeta(doc_key="k", title="t", doc_type="notes")
    assert meta.doc_key == "k"
    assert meta.authors == []


def test_chunk_policy_defaults() -> None:
    policy = ChunkPolicy(target_tokens=800, max_tokens=1200, overlap_tokens=100)
    assert policy.strategy == "structural"
    assert policy.keep_equation_with_context is True
    assert policy.never_split_within == ["equation", "table"]
