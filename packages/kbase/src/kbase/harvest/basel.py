"""Basel Framework chapter pages (bis.org) → the Markdown dialect `MarkdownParser` reads
(WP20 §5.1, §6.1).

Each numbered paragraph becomes its own heading (`#### MAR21.4`), so its chunks carry
the id (`kbase.regulatory.paragraph_id`). The chapter's headings (`h4`) and sub-headings
(muted lines) become `##` / `###`. Footnotes and FAQs are written inside the paragraph
that holds them. Formulas are SVG glyph outlines with no text: they become a
`[formula: <image name>]` placeholder, never guessed.

Fetching follows bis.org's robots.txt: chapter pages only (the standard index pages and
`/sites/default/files/`, where the formula images live, are disallowed). Any chapter
page lists every chapter of the framework, so discovery starts from one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

import yaml
from bs4 import BeautifulSoup
from bs4.element import NavigableString, PageElement, Tag
from corelib.errors import DependencyError
from pydantic import BaseModel

from kbase.harvest.http import RawResponse

BIS_ROOT = "https://www.bis.org"
_CHAPTER_HREF_RE = re.compile(
    r"^/committees/bcbs/basel-framework/standard/(?P<std>[a-z]+)/(?P<num>\d+)"
    r"/inforce/(?P<inforce>\d{4}-\d{2}-\d{2})/published/(?P<published>\d{4}-\d{2}-\d{2})$"
)
_PARAGRAPH_ID_RE = re.compile(r"^\d{1,3}\.\d{1,3}[a-z]?$")
_EFFECTIVE_RE = re.compile(r"Effective as of:\s*(\d{1,2} \w{3} \d{4})")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class ChapterRef:
    code: str  # MAR21
    standard: str  # MAR
    title: str
    url: str
    in_force: date
    published: date


@dataclass(frozen=True)
class ChapterConversion:
    markdown: str
    code: str
    title: str
    summary: str
    effective: date | None
    paragraphs: int
    formulas: int
    tables: int
    footnotes: int
    faqs: int


def _list_label(depth: int, index: int) -> str:
    """BIS numbering: (1), then (a), then (i)."""
    if depth == 0 or index > 26:
        return f"({index})"
    if depth == 1:
        return f"({chr(ord('a') + index - 1)})"
    return f"({_roman(index)})"


def _roman(n: int) -> str:
    numerals = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for value, symbol in numerals:
        while n >= value:
            out += symbol
            n -= value
    return out


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def _classes(el: Tag) -> set[str]:
    value = el.get("class")
    if isinstance(value, str):
        return {value}
    return set(value or [])


def chapter_refs(html: str) -> list[ChapterRef]:
    """Every chapter a Basel Framework page links to, in page order, once each."""
    soup = BeautifulSoup(html, "html.parser")
    refs: dict[str, ChapterRef] = {}
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        match = _CHAPTER_HREF_RE.match(str(anchor["href"]))
        if not match:
            continue
        code = f"{match['std'].upper()}{match['num']}"
        label = anchor.select_one(".accordion-subitem__label")
        if code in refs or label is None:
            continue
        refs[code] = ChapterRef(
            code=code,
            standard=match["std"].upper(),
            title=_clean(label.get_text(" ")),
            url=BIS_ROOT + str(anchor["href"]),
            in_force=date.fromisoformat(match["inforce"]),
            published=date.fromisoformat(match["published"]),
        )
    return list(refs.values())


class _Converter:
    def __init__(self, page_url: str) -> None:
        self.page_url = page_url
        self.formulas = 0
        self.tables = 0
        self.footnotes = 0
        self.faqs = 0

    # -- inline -----------------------------------------------------------------
    def inline(self, node: PageElement) -> str:
        if isinstance(node, NavigableString):
            return str(node)
        if not isinstance(node, Tag):
            return ""
        if node.name == "img":
            self.formulas += 1
            src = node.get("src")
            name = str(src).rsplit("/", 1)[-1] if src else ""
            return f" [formula: {name}] " if name else " [formula] "
        if node.name == "br":
            return " "
        if node.name in {"script", "style", "button", "svg"}:
            return ""
        if "footnote__citations-wrapper" in _classes(node):
            marks = [_clean(a.get_text()) for a in node.find_all("a")]
            return "".join(f"[^{m}]" for m in marks if m)
        if node.name in {"sup"} and node.find("a", class_="footnote-link"):
            return "".join(f"[^{_clean(a.get_text())}]" for a in node.find_all("a"))
        if node.name in {"sub", "sup"}:
            inner = _clean("".join(self.inline(c) for c in node.children))
            return f"{'_' if node.name == 'sub' else '^'}{{{inner}}}" if inner else ""
        return "".join(self.inline(child) for child in node.children)

    # -- blocks -----------------------------------------------------------------
    def table(self, table: Tag) -> str | None:
        rows: list[list[str]] = []
        for row in table.find_all("tr"):
            if not isinstance(row, Tag):
                continue
            cells: list[str] = []
            for cell in row.find_all(["td", "th"], recursive=False):
                if not isinstance(cell, Tag):
                    continue
                text = _clean(self.inline(cell)).replace("|", "\\|")
                span = cell.get("colspan")
                cells.append(text)
                if isinstance(span, str) and span.isdigit():
                    cells.extend([""] * (int(span) - 1))
            if any(cells):
                rows.append(cells)
        if len(rows) < 2:
            return None
        self.tables += 1
        width = max(len(r) for r in rows)
        padded = [r + [""] * (width - len(r)) for r in rows]
        lines = ["| " + " | ".join(padded[0]) + " |", "|" + "---|" * width]
        lines += ["| " + " | ".join(r) + " |" for r in padded[1:]]
        return "\n".join(lines)

    def list_items(self, el: Tag, depth: int, out: list[str]) -> None:
        ordered = el.name == "ol"
        for index, item in enumerate(el.find_all("li", recursive=False), start=1):
            if not isinstance(item, Tag):
                continue
            own = "".join(
                self.inline(c)
                for c in item.children
                if not (isinstance(c, Tag) and c.name in {"ol", "ul", "table", "details"})
            )
            prefix = _list_label(depth, index) if ordered else "-"
            text = _clean(own)
            if text:
                out.append(_escape(f"{prefix} {text}"))
            for child in item.children:
                if isinstance(child, Tag) and child.name in {"ol", "ul"}:
                    self.list_items(child, depth + 1, out)
                elif isinstance(child, Tag) and child.name == "table":
                    md = self.table(child)
                    if md:
                        out.append(md)

    def notes(self, details: Tag) -> list[str]:
        """Footnotes (`[^1]: …`) and FAQs (`FAQ1: …`) of one paragraph."""
        out: list[str] = []
        is_faq = "faq" in _clean(details.summary.get_text()).lower() if details.summary else False
        for row in details.select("table.footnote-list tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 2:
                continue
            ident = _clean(cells[0].get_text())
            parts = [
                _clean(self.inline(p))
                for p in cells[1].find_all(["p", "li"])
                if isinstance(p, Tag) and _clean(self.inline(p))
            ] or [_clean(self.inline(cells[1]))]
            if is_faq:
                self.faqs += 1
                out.append(_escape(f"{ident}: {parts[0]}"))
                out.extend(_escape(p) for p in parts[1:])
            else:
                self.footnotes += 1
                out.append(_escape(f"[^{ident}]: {' '.join(parts)}"))
        return out

    def body(self, body: Tag) -> list[str]:
        out: list[str] = []
        notes: list[str] = []
        for child in body.children:
            if isinstance(child, NavigableString):
                if child.strip():
                    out.append(_escape(_clean(str(child))))
                continue
            if not isinstance(child, Tag):
                continue
            if child.name == "details":
                notes.extend(self.notes(child))
            elif child.name in {"ol", "ul"}:
                self.list_items(child, 0, out)
            elif child.name == "table":
                md = self.table(child)
                if md:
                    out.append(md)
            elif child.name == "div" and child.find("table") and not child.find("details"):
                for table in child.find_all("table"):
                    if isinstance(table, Tag):
                        md = self.table(table)
                        if md:
                            out.append(md)
            else:
                text = _clean(self.inline(child))
                if text:
                    out.append(_escape(text))
        return out + notes


def _escape(line: str) -> str:
    """A line starting with these would be re-read as structure by `MarkdownParser`."""
    return "\\" + line if line.startswith(("#", "$$", "|", "<!--")) else line


def _effective(text: str) -> date | None:
    match = _EFFECTIVE_RE.search(text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%d %b %Y").date()
    except ValueError:
        return None


def convert_chapter(html: str, code: str, page_url: str = BIS_ROOT) -> ChapterConversion:
    """One chapter page → Markdown with a heading per numbered paragraph."""
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("div.chapters-content")
    if content is None:
        raise ValueError(f"{code}: no chapters-content block, not a Basel Framework chapter page")

    card = soup.select_one("div.card-summary")
    card_text = _clean(card.get_text(" ")) if card else ""
    title = code
    summary = ""
    if card is not None:
        heading = card.find(["h1", "h2", "h3"])
        heading_text = _clean(heading.get_text(" ")) if isinstance(heading, Tag) else ""
        title = heading_text or code
        para = card.find("p")
        summary = _clean(para.get_text(" ")) if isinstance(para, Tag) else ""
    if not title.startswith(code):
        title = f"{code} {title}".strip()

    converter = _Converter(page_url)
    blocks: list[str] = [f"# {title}"]
    if summary:
        blocks.append(_escape(summary))
    paragraphs = 0
    for item in content.select("div.framework-paragraph"):
        pid = str(item.get("id") or "")
        if _PARAGRAPH_ID_RE.match(pid):
            paragraphs += 1
            blocks.append(f"#### {code.rstrip('0123456789')}{pid}")
            body = item.select_one("div.paragraph-body")
            if body is not None:
                blocks.extend(converter.body(body))
            continue
        h4 = item.find("h4")
        if isinstance(h4, Tag):
            text = _clean(h4.get_text(" "))
            if text:
                blocks.append(f"## {text}")
            continue
        muted = item.select_one(".text-muted")
        if isinstance(muted, Tag):
            text = _clean(muted.get_text(" "))
            if text:
                blocks.append(f"### {text}")

    return ChapterConversion(
        markdown="\n\n".join(blocks) + "\n",
        code=code,
        title=title,
        summary=summary,
        effective=_effective(card_text),
        paragraphs=paragraphs,
        formulas=converter.formulas,
        tables=converter.tables,
        footnotes=converter.footnotes,
        faqs=converter.faqs,
    )


# Topic of each chapter (WP20 §5.2); a chapter not listed takes its standard's default.
_STANDARD_TOPICS = {
    "SCO": "reg-scope", "CAP": "reg-capital-definition", "RBC": "reg-capital-requirements",
    "CRE": "reg-credit-risk", "MAR": "reg-market-risk", "OPE": "reg-op-risk",
    "LEV": "reg-leverage", "LEX": "reg-large-exposures", "LCR": "reg-liquidity",
    "NSF": "reg-liquidity", "SRP": "reg-supervisory-review", "DIS": "reg-disclosure",
    "BCP": "reg-core-principles", "MGN": "reg-margin-requirements",
}  # fmt: skip
_CHAPTER_TOPICS = {
    **{f"CRE{n}": "reg-credit-sa" for n in (20, 21, 22)},
    **{f"CRE{n}": "reg-irb" for n in (30, 31, 32, 33, 34, 35, 36)},
    **{f"CRE{n}": "reg-securitisation" for n in (40, 41, 42, 43, 44, 45)},
    "CRE50": "reg-ccr", "CRE51": "reg-ccr", "CRE52": "reg-ccr-sa-ccr", "CRE53": "reg-ccr-imm",
    "CRE54": "reg-ccr-ccp", "CRE55": "reg-ccr", "CRE56": "reg-ccr",
    **{f"MAR{n}": "reg-frtb-scope" for n in (10, 11, 12)},
    **{f"MAR{n}": "reg-frtb-sa" for n in (20, 21, 22, 23)},
    **{f"MAR{n}": "reg-frtb-ima" for n in (30, 31, 32, 33)},
    "MAR40": "reg-frtb-simplified", "MAR50": "reg-cva-capital",
    "RBC20": "reg-capital-requirements", "RBC40": "reg-gsib",
}  # fmt: skip
_MANIFEST_HEADER = (
    "# Generated by `kbase harvest-basel` (WP20), then read by `kbase ingest`. Paths are\n"
    "# relative to AGX_PATHS_DOCUMENTS_DIR. Basel Framework chapters, one document per\n"
    "# chapter, the version in force; re-running replaces an entry by its doc_key.\n"
)
LICENSE = (
    "(c) Bank for International Settlements; excerpts may be reproduced with the source "
    "stated. Kept local, not redistributed."
)


def topic_for(code: str, standard: str) -> str:
    return _CHAPTER_TOPICS.get(code, _STANDARD_TOPICS.get(standard, "reg-other"))


def doc_key_for(code: str) -> str:
    return f"bcbs-{code.lower()}"


def manifest_entry(
    ref: ChapterRef, conversion: ChapterConversion, md_path: str
) -> dict[str, object]:
    return {
        "doc_key": doc_key_for(ref.code),
        "path": md_path,
        "title": conversion.title,
        "authors": ["Basel Committee on Banking Supervision"],
        "year": ref.published.year,
        "doc_type": "standard",
        "topic": topic_for(ref.code, ref.standard),
        "source_url": ref.url,
        "license": LICENSE,
        "valid_from": (conversion.effective or ref.in_force).isoformat(),
    }


def upsert_manifest(path: Path, entries: list[dict[str, object]]) -> tuple[int, int]:
    """Writes `entries` into the regulation manifest, replacing those with the same
    doc_key; returns (added, replaced). Other entries are kept in their order."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
    documents: list[dict[str, object]] = []
    if isinstance(raw, dict):
        documents = [d for d in raw.get("documents") or [] if isinstance(d, dict)]
    index = {d.get("doc_key"): i for i, d in enumerate(documents)}
    added = replaced = 0
    for entry in entries:
        position = index.get(entry["doc_key"])
        if position is None:
            index[entry["doc_key"]] = len(documents)
            documents.append(entry)
            added += 1
        else:
            documents[position] = entry
            replaced += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(
        {"collection": "regulation", "documents": documents},
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )
    path.write_text(_MANIFEST_HEADER + "\n" + body, encoding="utf-8")
    return added, replaced


class BaselReport(BaseModel):
    chapters_found: int
    chapters_selected: list[str]
    converted: list[str] = []
    failed: dict[str, str] = {}
    paragraphs: int = 0
    formulas: int = 0
    manifest_added: int = 0
    manifest_replaced: int = 0
    requests: int = 0


class _Getter(Protocol):
    requests_made: int

    def get(self, url: str) -> RawResponse: ...


def harvest_basel(
    client: _Getter,
    *,
    seed_url: str,
    standards: list[str],
    chapters: list[str],
    documents_dir: Path,
    html_dir: str,
    md_dir: str,
    manifest: Path,
    dry_run: bool = False,
) -> BaselReport:
    """Fetches the selected chapters (by standard, or by code), converts them, and
    upserts their manifest entries. `dry_run` only lists what would be fetched."""
    seed = client.get(seed_url)
    if seed.status != 200:
        raise DependencyError(
            f"Basel Framework seed page returned HTTP {seed.status}: {seed_url}",
            details={"url": seed_url, "status": seed.status},
        )
    refs = chapter_refs(seed.body.decode("utf-8", errors="replace"))
    wanted_std = {s.upper() for s in standards}
    wanted_codes = {c.upper() for c in chapters}
    selected = [r for r in refs if r.standard in wanted_std or r.code in wanted_codes]
    report = BaselReport(chapters_found=len(refs), chapters_selected=[r.code for r in selected])
    if dry_run:
        report.requests = client.requests_made
        return report

    entries: list[dict[str, object]] = []
    for ref in selected:
        response = client.get(ref.url)
        if response.status != 200:
            report.failed[ref.code] = f"HTTP {response.status}"
            continue
        html = response.body.decode("utf-8", errors="replace")
        try:
            conversion = convert_chapter(html, ref.code, ref.url)
        except ValueError as exc:
            report.failed[ref.code] = str(exc)
            continue
        if conversion.paragraphs == 0:
            report.failed[ref.code] = "no numbered paragraph found"
            continue
        html_path = documents_dir / html_dir / f"{ref.code}.html"
        md_rel = f"{md_dir.rstrip('/')}/{ref.code}.md"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8")
        (documents_dir / md_rel).parent.mkdir(parents=True, exist_ok=True)
        (documents_dir / md_rel).write_text(conversion.markdown, encoding="utf-8")
        entries.append(manifest_entry(ref, conversion, md_rel))
        report.converted.append(ref.code)
        report.paragraphs += conversion.paragraphs
        report.formulas += conversion.formulas
    report.manifest_added, report.manifest_replaced = upsert_manifest(manifest, entries)
    report.requests = client.requests_made
    return report
