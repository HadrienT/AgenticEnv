"""Minimal contradiction signal (WP05 §7): distinct sources on the same top-k is
surfaced as a warning rather than silently picking one. Semantic contradiction
detection is out of scope for phase 1.
"""

from __future__ import annotations

from collections.abc import Sequence

from kbase.schemas import RetrievedChunk


def detect(chunks: Sequence[RetrievedChunk]) -> list[str]:
    documents = {c.citation.document for c in chunks}
    if len(documents) <= 1:
        return []
    joined = ", ".join(sorted(documents))
    return [f"potentially divergent sources in top results: {joined}"]
