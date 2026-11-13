"""Formulas for Basel Framework chapters (WP20 step 5b).

On bis.org every formula is an SVG of glyph outlines: the HTML converter leaves a
`[formula: <image>]` placeholder. The chapter PDF, read by MinerU, gives the formulas
as LaTeX but its prose is noisier (missing spaces, misread symbols). The merge keeps the
HTML text and puts each PDF formula in place of a placeholder of the same paragraph,
matched on the words that precede it. A placeholder with no convincing match stays;
the paragraph's unplaced PDF formulas are then listed after it, so none is lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HTML_PARAGRAPH_RE = re.compile(r"^#### ([A-Z]{3}\d{1,3}\.\d{1,3}[a-z]?)\s*$", re.MULTILINE)
_PDF_PARAGRAPH_RE = re.compile(r"^#{1,6}\s+(\d{1,3}\.\d{1,3}[a-z]?)\s*$", re.MULTILINE)
_PLACEHOLDER_RE = re.compile(r"\[formula(?:: [^\]]+)?\]")
_PDF_FORMULA_RE = re.compile(r"\$\$\s*(.+?)\s*\$\$|\$(.+?)\$", re.DOTALL)
_TOKEN_RE = re.compile(r"[a-z]{3,}|\d+(?:\.\d+)?")
_CONTEXT_WORDS = 6
_MIN_SCORE = 0.25
# MinerU writes `\mathsf{ S }`, `K _ { b }`: valid LaTeX, but noisy in a chunk.
_FONT_RE = re.compile(r"\\(?:mathsf|mathrm|sf|boldsymbol|mathbf)\s*")
_SPACES_RE = re.compile(r"\s+")
# `m a x`, `D e l t a`: MinerU spells words out letter by letter.
_SPELLED_RE = re.compile(r"(?<![\\A-Za-z])(?:[A-Za-z] ){1,}[A-Za-z](?![A-Za-z])")


@dataclass
class MergeStats:
    placeholders: int = 0
    placed: int = 0
    listed: int = 0  # PDF formulas appended after their paragraph, unplaced
    paragraphs_without_pdf: list[str] = field(default_factory=list)


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def clean_latex(latex: str) -> str:
    latex = _FONT_RE.sub("", latex)
    latex = _SPACES_RE.sub(" ", latex).strip()
    latex = _SPELLED_RE.sub(lambda m: m.group(0).replace(" ", ""), latex)
    return re.sub(r"\s*([_^{}(),=+\-])\s*", r"\1", latex)


@dataclass(frozen=True)
class _PdfFormula:
    latex: str
    before: tuple[str, ...]
    after: tuple[str, ...]


def _split(text: str, pattern: re.Pattern[str]) -> dict[str, str]:
    """Paragraph id (as matched) → its text, up to the next paragraph heading."""
    marks = list(pattern.finditer(text))
    return {
        m.group(1): text[m.end() : marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        for i, m in enumerate(marks)
    }


def _pdf_formulas(paragraph: str) -> list[_PdfFormula]:
    out: list[_PdfFormula] = []
    for match in _PDF_FORMULA_RE.finditer(paragraph):
        latex = match.group(1) or match.group(2) or ""
        if not latex.strip():
            continue
        before = _PDF_FORMULA_RE.sub(" ", paragraph[: match.start()])
        after = _PDF_FORMULA_RE.sub(" ", paragraph[match.end() :])
        out.append(
            _PdfFormula(
                clean_latex(latex),
                tuple(_tokens(before)[-_CONTEXT_WORDS:]),
                tuple(_tokens(after)[:_CONTEXT_WORDS]),
            )
        )
    return out


def _score(a: tuple[str, ...], b: tuple[str, ...]) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


def _match(before: tuple[str, ...], after: tuple[str, ...], formula: _PdfFormula) -> float:
    """The words before must agree, and those after too when both sides have some: one
    side alone places a formula a clause too early. A paragraph's last formula has
    nothing after it in the page, but often a page break or list item in the PDF."""
    score = _score(before, formula.before)
    if after and formula.after:
        score = min(score, _score(after, formula.after))
    return score


def _merge_paragraph(body: str, formulas: list[_PdfFormula], stats: MergeStats) -> str:
    placeholders = list(_PLACEHOLDER_RE.finditer(body))
    stats.placeholders += len(placeholders)
    used: set[int] = set()
    pointer = 0
    replacements: list[tuple[int, int, str]] = []
    for match in placeholders:
        before = tuple(_tokens(_PLACEHOLDER_RE.sub(" ", body[: match.start()]))[-_CONTEXT_WORDS:])
        after = tuple(_tokens(_PLACEHOLDER_RE.sub(" ", body[match.end() :]))[:_CONTEXT_WORDS])
        best, best_score = None, _MIN_SCORE
        for i in range(pointer, len(formulas)):
            score = _match(before, after, formulas[i])
            if score > best_score:
                best, best_score = i, score
        if best is None and len(placeholders) == len(formulas):
            # Same count: trust the order, if the words before share something.
            index = placeholders.index(match)
            if index >= pointer and _score(before, formulas[index].before) > 0:
                best = index
        if best is not None:
            used.add(best)
            pointer = best + 1
            replacements.append((match.start(), match.end(), f"${formulas[best].latex}$"))
            stats.placed += 1
    for start, end, text in reversed(replacements):
        body = body[:start] + text + body[end:]
    leftovers = [f for i, f in enumerate(formulas) if i not in used]
    if leftovers and _PLACEHOLDER_RE.search(body):
        stats.listed += len(leftovers)
        listing = "; ".join(f"${f.latex}$" for f in leftovers)
        body = body.rstrip("\n") + f"\n\nFormulas of this paragraph (from the PDF): {listing}\n\n"
    return body


def merge_formulas(html_markdown: str, pdf_markdown: str) -> tuple[str, MergeStats]:
    """The HTML chapter Markdown with its placeholders replaced by the PDF's formulas."""
    stats = MergeStats()
    pdf = {
        pid: _pdf_formulas(text) for pid, text in _split(pdf_markdown, _PDF_PARAGRAPH_RE).items()
    }
    marks = list(_HTML_PARAGRAPH_RE.finditer(html_markdown))
    if not marks:
        return html_markdown, stats
    pieces = [html_markdown[: marks[0].end()]]
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(html_markdown)
        body = html_markdown[mark.end() : end]
        local = mark.group(1).lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")  # MAR21.4 -> 21.4
        if _PLACEHOLDER_RE.search(body):
            if local in pdf:
                body = _merge_paragraph(body, pdf[local], stats)
            else:
                stats.placeholders += len(_PLACEHOLDER_RE.findall(body))
                stats.paragraphs_without_pdf.append(mark.group(1))
        pieces.append(body)
        if i + 1 < len(marks):
            pieces.append(html_markdown[end : marks[i + 1].end()])
    return "".join(pieces), stats
