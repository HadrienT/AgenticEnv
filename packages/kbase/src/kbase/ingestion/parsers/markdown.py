"""Structural Markdown parser: the concrete `Parser` implementation delivered by WP04.

Headings become the section tree; `$$...$$` blocks become atomic equation blocks
(never merged, never split, LaTeX preserved verbatim); GFM pipe tables become
atomic table blocks; everything else is paragraph text. Real PDF parsing is a
separate `Parser` implementation to be added later — this one is offline,
dependency-free, and fully deterministic, which is what the ingestion pipeline
and its tests need first (WP04 §2, §3).
"""

from __future__ import annotations

import re
from pathlib import Path

from corelib.hashing import sha256_file

from kbase.schemas import ContentBlock, DocumentMeta, Equation, ParsedDocument, Section

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_PAGE_MARKER_RE = re.compile(r"^<!--\s*page:\s*(\d+)\s*-->$")
_SINGLE_LINE_EQ_RE = re.compile(r"^\$\$(.+?)\$\$\s*(?:\(([^)]+)\))?$")
_BLOCK_EQ_CLOSE_RE = re.compile(r"^\$\$\s*(?:\(([^)]+)\))?$")
_TAG_RE = re.compile(r"\\tag\{([^}]+)\}")
_TABLE_SEPARATOR_RE = re.compile(r"^\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?$")
_TABLE_CAPTION_RE = re.compile(r"(?i)^table\b")
_GREEK_MACROS = frozenset(
    {
        "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota",
        "kappa", "lambda", "mu", "nu", "xi", "omicron", "pi", "rho", "sigma", "tau",
        "upsilon", "phi", "chi", "psi", "omega",
    }
)  # fmt: skip


def _is_table_row(stripped: str) -> bool:
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _extract_symbols(latex: str) -> list[str]:
    """Heuristic symbol extraction: Greek LaTeX macros + bare single-letter variables."""
    macros = {m.lower() for m in re.findall(r"\\([A-Za-z]+)", latex)}
    greek = sorted(m for m in macros if m in _GREEK_MACROS)
    latin = sorted(set(re.findall(r"(?<![A-Za-z\\])([A-Za-z])(?:_\d+)?(?![A-Za-z])", latex)))
    return greek + latin


class MarkdownParser:
    """`Parser` for `.md`/`.markdown`/`.txt` sources."""

    name = "markdown"
    version = "1"

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() in {".md", ".markdown", ".txt"}

    def parse(self, path: Path, meta: DocumentMeta) -> ParsedDocument:
        lines = path.read_text(encoding="utf-8").splitlines()
        sections: list[Section] = []
        blocks: list[ContentBlock] = []
        counters: list[int] = []
        current_section_id: str | None = None
        current_page: int | None = None
        max_page: int | None = None
        paragraph_buf: list[str] = []

        def flush_paragraph() -> None:
            if not paragraph_buf:
                return
            text = "\n".join(paragraph_buf).strip()
            paragraph_buf.clear()
            if text:
                blocks.append(
                    ContentBlock(
                        kind="text",
                        text=text,
                        section_id=current_section_id,
                        page_start=current_page,
                        page_end=current_page,
                    )
                )

        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            stripped = line.strip()

            page_match = _PAGE_MARKER_RE.match(stripped)
            if page_match:
                flush_paragraph()
                current_page = int(page_match.group(1))
                max_page = current_page if max_page is None else max(max_page, current_page)
                i += 1
                continue

            heading_match = _HEADING_RE.match(line)
            if heading_match:
                flush_paragraph()
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                if level > len(counters):
                    counters.extend([0] * (level - len(counters)))
                counters = counters[:level]
                counters[level - 1] += 1
                path_str = ".".join(str(c) for c in counters)
                parent_path = ".".join(str(c) for c in counters[:-1]) if level > 1 else None
                sections.append(
                    Section(
                        section_id=path_str,
                        parent_id=parent_path,
                        level=level,
                        ordinal=counters[-1],
                        title=title,
                        page_start=current_page,
                        page_end=current_page,
                        path=path_str,
                    )
                )
                current_section_id = path_str
                i += 1
                continue

            next_line_is_separator = i + 1 < n and _TABLE_SEPARATOR_RE.match(lines[i + 1].strip())
            if _is_table_row(stripped) and next_line_is_separator:
                caption = None
                if paragraph_buf and _TABLE_CAPTION_RE.match(paragraph_buf[-1].strip()):
                    caption = paragraph_buf.pop().strip()
                flush_paragraph()
                table_lines = [line, lines[i + 1]]
                j = i + 2
                while j < n and _is_table_row(lines[j].strip()):
                    table_lines.append(lines[j])
                    j += 1
                table_md = "\n".join(table_lines)
                blocks.append(
                    ContentBlock(
                        kind="table",
                        text=table_md,
                        section_id=current_section_id,
                        page_start=current_page,
                        page_end=current_page,
                        table_caption=caption,
                        table_content_md=table_md,
                    )
                )
                i = j
                continue

            single_eq = _SINGLE_LINE_EQ_RE.match(stripped)
            if single_eq:
                context_before = paragraph_buf[-1].strip() if paragraph_buf else None
                flush_paragraph()
                latex_raw = single_eq.group(1).strip()
                eq_number = single_eq.group(2)
                context_after = lines[i + 1].strip() if i + 1 < n and lines[i + 1].strip() else None
                blocks.append(
                    ContentBlock(
                        kind="equation",
                        text=latex_raw,
                        section_id=current_section_id,
                        page_start=current_page,
                        page_end=current_page,
                        equation=Equation(
                            latex=latex_raw,
                            equation_number=eq_number,
                            page=current_page,
                            symbols=_extract_symbols(latex_raw),
                        ),
                        context_before=context_before,
                        context_after=context_after,
                    )
                )
                i += 1
                continue

            if stripped == "$$":
                context_before = paragraph_buf[-1].strip() if paragraph_buf else None
                flush_paragraph()
                eq_lines: list[str] = []
                j = i + 1
                close_match = None
                while j < n:
                    close_match = _BLOCK_EQ_CLOSE_RE.match(lines[j].strip())
                    if close_match:
                        break
                    eq_lines.append(lines[j])
                    j += 1
                latex_raw = "\n".join(eq_lines).strip()
                eq_number = close_match.group(1) if close_match else None
                tag_match = _TAG_RE.search(latex_raw)
                if tag_match:
                    eq_number = eq_number or tag_match.group(1)
                    latex_raw = latex_raw.replace(tag_match.group(0), "").strip()
                context_after = lines[j + 1].strip() if j + 1 < n and lines[j + 1].strip() else None
                blocks.append(
                    ContentBlock(
                        kind="equation",
                        text=latex_raw,
                        section_id=current_section_id,
                        page_start=current_page,
                        page_end=current_page,
                        equation=Equation(
                            latex=latex_raw,
                            equation_number=eq_number,
                            page=current_page,
                            symbols=_extract_symbols(latex_raw),
                        ),
                        context_before=context_before,
                        context_after=context_after,
                    )
                )
                i = j + 1
                continue

            if stripped == "":
                flush_paragraph()
            else:
                paragraph_buf.append(line)
            i += 1

        flush_paragraph()

        return ParsedDocument(
            meta=meta,
            version="1",
            sha256=sha256_file(path),
            page_count=max_page,
            sections=sections,
            blocks=blocks,
            parser_name=self.name,
            parser_version=self.version,
        )
