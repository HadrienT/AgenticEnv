"""Structural chunking: section-scoped text grouping; equations/tables are atomic,
never split, never merged with anything else (WP04 §4, rules K1-K7)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from corelib.hashing import sha256_obj
from corelib.ids import new_id

from kbase.schemas import Chunk, ChunkEquation, ChunkPolicy, ContentBlock, ParsedDocument


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


def approx_tokens(text: str) -> int:
    """Model-token estimate (~4 characters per token): whitespace words undercount
    LaTeX, where one `word` can be dozens of tokens."""
    return len(text) // 4 + 1


def render_equation(latex: str, number: str | None) -> str:
    return f"$$ {latex} $$" + (f" ({number})" if number else "")


def _render_block(block: ContentBlock) -> str:
    if block.kind == "equation" and block.equation is not None:
        return render_equation(block.equation.latex, block.equation.equation_number)
    if block.kind == "table":
        table = block.table_content_md or block.text
        return f"{block.table_caption}\n{table}" if block.table_caption else table
    return block.text


def _tail_sentences(text: str, budget: int) -> str:
    """The last whole sentences of `text` within `budget` tokens (overlap)."""
    if budget <= 0:
        return ""
    taken: list[str] = []
    used = 0
    for sentence in reversed([s for s in _SENTENCE_SPLIT_RE.split(text) if s]):
        cost = approx_tokens(sentence)
        if taken and used + cost > budget:
            break
        if cost > budget:
            break
        taken.insert(0, sentence)
        used += cost
    return " ".join(taken)


@dataclass
class _Piece:
    text: str
    tokens: int
    block: ContentBlock | None  # None for a heading line


class SectionChunker:
    """`strategy == "section"`: chunks follow the section tree and carry everything in
    it, equations and tables included, in reading order.

    - a section's heading opens its first chunk, so a chunk reads like the book;
    - a chunk is closed once it reaches `target_tokens` and the next piece would push
      it past; a paragraph longer than `max_tokens` is split at sentences;
    - a section boundary closes the chunk, unless the chunk is still under
      `min_tokens` and the next section is in the same chapter: short sibling
      sections are then merged rather than left as fragments;
    - a chunk continuing the same section starts with the last sentences of the
      previous one (`overlap_tokens`);
    - equations are never split and stay next to the prose that introduces them; each
      is still recorded (`Chunk.equations`) for lookups by number.
    """

    def chunk(self, doc: ParsedDocument, policy: ChunkPolicy) -> list[Chunk]:
        sections = {s.section_id: s for s in doc.sections}

        def chapter_of(section_id: str | None) -> str | None:
            current = sections.get(section_id) if section_id else None
            while current is not None and current.parent_id is not None:
                parent = sections.get(current.parent_id)
                if parent is None or parent.level <= 1:
                    break
                current = parent
            return current.section_id if current else None

        chunks: list[Chunk] = []
        parts: list[_Piece] = []
        state: dict[str, str | int | None] = {"section": None, "chapter": None}

        def tokens() -> int:
            return sum(p.tokens for p in parts)

        def flush(*, overlap: bool) -> None:
            content_parts = [p for p in parts if p.block is not None]
            if not content_parts:
                parts.clear()
                return
            content = "\n\n".join(p.text for p in parts)
            blocks = [p.block for p in content_parts if p.block is not None]
            pages = [b.page_start for b in blocks if b.page_start is not None]
            page_ends = [b.page_end for b in blocks if b.page_end is not None]
            equations = [
                ChunkEquation(
                    equation=b.equation,
                    context_before=b.context_before,
                    context_after=b.context_after,
                )  # fmt: skip
                for b in blocks
                if b.kind == "equation" and b.equation is not None
            ]
            chunks.append(
                Chunk(
                    chunk_id=new_id(),
                    document_version_id="",
                    section_id=blocks[0].section_id,
                    ordinal=len(chunks),
                    kind="text",
                    content=content,
                    n_tokens=approx_tokens(content),
                    page_start=min(pages) if pages else None,
                    page_end=max(page_ends) if page_ends else None,
                    has_equations=bool(equations),
                    valid_from=None,
                    valid_until=None,
                    sha256=sha256_obj(content),
                    equations=equations,
                )
            )
            last_text = next(
                (p for p in reversed(content_parts) if p.block and p.block.kind == "text"), None
            )
            parts.clear()
            if overlap and last_text is not None:
                tail = _tail_sentences(last_text.text, policy.overlap_tokens)
                if tail and tail != last_text.text:
                    parts.append(_Piece(tail, approx_tokens(tail), last_text.block))

        def add(piece: _Piece) -> None:
            if (
                parts
                and tokens() + piece.tokens > policy.target_tokens
                and (tokens() >= policy.min_tokens)
            ):
                flush(overlap=True)
            parts.append(piece)

        for block in doc.blocks:
            if block.section_id != state["section"]:
                chapter = chapter_of(block.section_id)
                if parts and (tokens() >= policy.min_tokens or chapter != state["chapter"]):
                    flush(overlap=False)
                state["section"], state["chapter"] = block.section_id, chapter
                section = sections.get(block.section_id) if block.section_id else None
                if section is not None and section.level > 1:
                    heading = f"{'#' * section.level} {section.title}"
                    parts.append(_Piece(heading, approx_tokens(heading), None))
            rendered = _render_block(block)
            if not rendered.strip():
                continue
            cost = approx_tokens(rendered)
            if block.kind == "text" and cost > policy.max_tokens:
                for sentence_group in _split_by_tokens(rendered, policy.max_tokens):
                    add(_Piece(sentence_group, approx_tokens(sentence_group), block))
            elif block.kind == "table" and cost > policy.max_tokens:
                for table_part in _split_table(block, policy.max_tokens):
                    add(_Piece(table_part, approx_tokens(table_part), block))
            else:
                add(_Piece(rendered, cost, block))
        flush(overlap=False)
        return chunks


def _split_table(block: ContentBlock, max_tokens: int) -> list[str]:
    """A table too long for one chunk, cut between rows; every part repeats the caption
    and the header, so each reads on its own. Big numeric result tables are the case:
    digits cost far more tokens per character than prose (an 18,000-character table is
    over 6,000 tokens, past what the embedding model takes in one pass)."""
    lines = (block.table_content_md or block.text).splitlines()
    header = (
        lines[:2]
        if len(lines) > 1 and set(lines[1].replace("|", "").strip()) <= set("-: ")
        else lines[:1]
    )
    rows = lines[len(header) :]
    caption = block.table_caption
    parts: list[str] = []
    current: list[str] = []

    def emit() -> None:
        title = caption if not parts or caption is None else f"{caption} (continued)"
        parts.append("\n".join(([title] if title else []) + header + current))

    budget = max_tokens - approx_tokens("\n".join(([caption] if caption else []) + header))
    used = 0
    for row in rows:
        cost = approx_tokens(row)
        if current and used + cost > budget:
            emit()
            current, used = [], 0
        current.append(row)
        used += cost
    if current or not parts:
        emit()
    return parts


def _split_by_tokens(text: str, max_tokens: int) -> list[str]:
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s]
    groups: list[str] = []
    buf: list[str] = []
    used = 0
    for sentence in sentences:
        cost = approx_tokens(sentence)
        if buf and used + cost > max_tokens:
            groups.append(" ".join(buf))
            buf, used = [], 0
        buf.append(sentence)
        used += cost
    if buf:
        groups.append(" ".join(buf))
    return groups or [text]
