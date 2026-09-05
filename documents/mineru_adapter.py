"""Adapts a MinerU `*_content_list_v2.json` into the Markdown dialect kbase's
`MarkdownParser` expects (blueprint/wp/WP04-kbase-ingestion.md): `$$...$$` display
equations with `\\tag{N}` numbering, GFM pipe tables, `<!-- page: N -->` markers.

MinerU systematically emits a space before LaTeX brace groups (`\\tag {1}`,
`\\frac {1}{2}`) which is cosmetically harmless in real LaTeX but breaks kbase's
`_TAG_RE`/symbol regexes, so every equation is normalized before being written out.

Blank-line placement matters: kbase's parser treats a blank line as a hard flush,
which is exactly how it captures `context_before`/`context_after` for an equation.
A blank line is therefore never inserted between a paragraph and an immediately
adjacent display equation (so context survives) but always inserted between two
adjacent equations (otherwise the second equation's opening `$$` would be
misread as `context_after` for the first).

Usage: python mineru_adapter.py <content_list_v2.json> <output.md>
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

_CMD_BRACE_SPACE_RE = re.compile(r"(\\[a-zA-Z]+)\s+\{")
_WS_RE = re.compile(r"[ \t]+")


def normalize_latex(latex: str) -> str:
    return _CMD_BRACE_SPACE_RE.sub(r"\1{", latex).strip()


def render_runs(runs: list[dict]) -> str:
    parts: list[str] = []
    for run in runs:
        kind = run.get("type")
        content = run.get("content", "")
        if kind == "equation_inline":
            parts.append(f"${normalize_latex(content)}$")
        else:
            parts.append(str(content))
    return _WS_RE.sub(" ", "".join(parts)).strip()


class _TableHTMLToGFM(HTMLParser):
    """Minimal HTML table -> GFM pipe table. Ignores rowspan/colspan (rare, and
    tables are an explicitly secondary-priority fidelity target for this corpus)."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            text = "".join(self._cell).strip().replace("|", "\\|")
            self._row.append(text)
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def html_table_to_gfm(html: str) -> str:
    parser = _TableHTMLToGFM()
    parser.feed(html)
    rows = [r for r in parser.rows if r]
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join([" --- "] * ncols) + "|"]
    lines.extend("| " + " | ".join(r) + " |" for r in rows[1:])
    return "\n".join(lines)


def _sep_needed(prev_kind: str | None, kind: str) -> bool:
    if prev_kind is None:
        return False
    if {prev_kind, kind} == {"para", "eq"}:
        return False
    return True


def convert(content_list_path: Path, output_path: Path) -> list[str]:
    pages = json.loads(content_list_path.read_text(encoding="utf-8"))
    out: list[str] = []
    warnings: list[str] = []
    prev_kind: str | None = None
    seen_heading = False

    def emit(kind: str, block_lines: list[str]) -> None:
        nonlocal prev_kind
        if not block_lines:
            return
        if _sep_needed(prev_kind, kind):
            out.append("")
        out.extend(block_lines)
        prev_kind = kind

    for page_idx, blocks in enumerate(pages, start=1):
        emit("other", [f"<!-- page: {page_idx} -->"])
        for block in blocks:
            btype = block.get("type")
            content = block.get("content", {})
            # kbase requires every chunk to belong to a section; content that
            # precedes the document's first heading (running header, journal
            # blurb, cover page) would otherwise be dropped as orphaned by
            # provenance.require_section. A synthetic heading keeps it instead.
            if not seen_heading and btype != "title" and btype not in ("page_number",):
                emit("other", ["# Front matter"])
                seen_heading = True
            if btype == "title":
                level = min(max(int(content.get("level", 2)), 1), 6)
                text = render_runs(content.get("title_content", []))
                emit("other", [f"{'#' * level} {text}"] if text else [])
                if text:
                    seen_heading = True
            elif btype == "paragraph":
                text = render_runs(content.get("paragraph_content", []))
                emit("para", [text] if text else [])
            elif btype in ("list", "index"):
                lines = [
                    render_runs(item.get("item_content", []))
                    for item in content.get("list_items", [])
                ]
                emit("other", [line for line in lines if line])
            elif btype in ("algorithm", "code"):
                # MinerU's layout detector uses these labels for boxed/highlighted
                # text (worked examples, callouts) as much as literal code or
                # pseudocode; content shape matches a plain paragraph either way.
                key = f"{btype}_content"
                emit("para", [render_runs(content.get(key, []))])
            elif btype == "page_footnote":
                emit("other", [render_runs(content.get("page_footnote_content", []))])
            elif btype == "page_aside_text":
                emit("other", [render_runs(content.get("page_aside_text_content", []))])
            elif btype == "page_footer":
                emit("other", [render_runs(content.get("page_footer_content", []))])
            elif btype in ("page_number", "page_header"):
                pass  # pure page furniture, no content value
            elif btype == "equation_interline":
                latex = normalize_latex(content.get("math_content", ""))
                emit("eq", ["$$", latex, "$$"] if latex else [])
            elif btype in ("image", "chart"):
                caption_key = "chart_caption" if btype == "chart" else "image_caption"
                caption = render_runs(content.get(caption_key, []))
                emit("other", [f"Figure: {caption}"] if caption else [])
            elif btype == "table":
                caption = render_runs(content.get("table_caption", []))
                gfm = html_table_to_gfm(content.get("html", ""))
                lines = ([f"Table: {caption}"] if caption else []) + ([gfm] if gfm else [])
                if not gfm:
                    warnings.append(f"page {page_idx}: table could not be converted to GFM")
                emit("other", lines)
            else:
                warnings.append(f"page {page_idx}: unknown block type '{btype}' skipped")

    output_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return warnings


if __name__ == "__main__":
    warnings = convert(Path(sys.argv[1]), Path(sys.argv[2]))
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
