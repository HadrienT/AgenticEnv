"""Structural chunking: section-scoped text grouping; equations/tables are atomic,
never split, never merged with anything else (WP04 §4, rules K1-K7)."""

from __future__ import annotations

import re
from typing import Protocol

from corelib.hashing import sha256_obj
from corelib.ids import new_id

from kbase.schemas import Chunk, ChunkPolicy, ParsedDocument


class Chunker(Protocol):
    def chunk(self, doc: ParsedDocument, policy: ChunkPolicy) -> list[Chunk]: ...


def _n_tokens(text: str) -> int:
    """Whitespace-word count; a real tokenizer is deferred to a later WP (approximation)."""
    return len(text.split())


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_oversized_text(text: str, max_tokens: int) -> list[str]:
    """K6: splits an over-long paragraph at sentence boundaries, never mid-sentence."""
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s]
    parts: list[str] = []
    buf: list[str] = []
    buf_tokens = 0
    for sentence in sentences:
        s_tokens = _n_tokens(sentence)
        if buf and buf_tokens + s_tokens > max_tokens:
            parts.append(" ".join(buf))
            buf, buf_tokens = [], 0
        buf.append(sentence)
        buf_tokens += s_tokens
    if buf:
        parts.append(" ".join(buf))
    return parts or [text]


def _overlap_prefix(text: str, overlap_tokens: int) -> str:
    """K4: controlled overlap carried into the next text chunk, word-based."""
    words = text.split()
    if overlap_tokens <= 0 or not words:
        return ""
    return " ".join(words[-overlap_tokens:])


class StructuralChunker:
    """Phase-1 `Chunker` (blueprint 03-INTERFACES.md §3.2: `strategy == "structural"`)."""

    def chunk(self, doc: ParsedDocument, policy: ChunkPolicy) -> list[Chunk]:
        chunks: list[Chunk] = []
        ordinal = 0
        text_buf: list[str] = []
        buf_tokens = 0
        buf_open = False
        buf_section_id: str | None = None
        buf_page_start: int | None = None
        buf_page_end: int | None = None
        pending_overlap = ""

        def flush_text() -> None:
            nonlocal ordinal, text_buf, buf_tokens, buf_open, pending_overlap
            if not text_buf:
                buf_open = False
                return
            content = "\n\n".join(text_buf)
            pieces = (
                _split_oversized_text(content, policy.max_tokens)
                if _n_tokens(content) > policy.max_tokens
                else [content]
            )
            for piece in pieces:
                chunks.append(
                    Chunk(
                        chunk_id=new_id(),
                        document_version_id="",
                        section_id=buf_section_id,
                        ordinal=ordinal,
                        kind="text",
                        content=piece,
                        n_tokens=_n_tokens(piece),
                        page_start=buf_page_start,
                        page_end=buf_page_end,
                        has_equations=False,
                        valid_from=None,
                        valid_until=None,
                        sha256=sha256_obj(piece),
                    )
                )
                ordinal += 1
            pending_overlap = _overlap_prefix(pieces[-1], policy.overlap_tokens)
            text_buf = []
            buf_tokens = 0
            buf_open = False

        for block in doc.blocks:
            if block.kind in ("equation", "table"):
                if buf_open:
                    flush_text()
                content = block.text
                chunks.append(
                    Chunk(
                        chunk_id=new_id(),
                        document_version_id="",
                        section_id=block.section_id,
                        ordinal=ordinal,
                        kind=block.kind,
                        content=content,
                        n_tokens=_n_tokens(content),
                        page_start=block.page_start,
                        page_end=block.page_end,
                        has_equations=block.kind == "equation",
                        valid_from=None,
                        valid_until=None,
                        sha256=sha256_obj(content),
                        equation=block.equation,
                        table_caption=block.table_caption,
                        table_content_md=block.table_content_md,
                        equation_context_before=block.context_before,
                        equation_context_after=block.context_after,
                    )
                )
                ordinal += 1
                continue

            if buf_open and block.section_id != buf_section_id:
                flush_text()
            if not buf_open:
                buf_section_id = block.section_id
                buf_page_start = block.page_start
                buf_page_end = block.page_end
                buf_open = True
                if pending_overlap:
                    text_buf.append(pending_overlap)
                    buf_tokens += _n_tokens(pending_overlap)
                    pending_overlap = ""
            text_buf.append(block.text)
            buf_tokens += _n_tokens(block.text)
            if block.page_end is not None:
                buf_page_end = block.page_end
            if buf_tokens >= policy.target_tokens:
                flush_text()

        if buf_open:
            flush_text()

        return chunks
