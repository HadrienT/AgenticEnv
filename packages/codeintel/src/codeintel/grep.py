from __future__ import annotations

import re
from bisect import bisect_right
from pathlib import Path

from codeintel.paths import cap_list, extract_context, to_relative
from codeintel.schemas import GrepMatch, GrepReport, GrepRequest

_SOURCE_SUFFIXES = {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h", ".ipp"}

_CODE, _LINE_COMMENT, _BLOCK_COMMENT, _STRING, _CHAR = range(5)
_COMMENT_CATEGORIES = {_LINE_COMMENT, _BLOCK_COMMENT}
_STRING_CATEGORIES = {_STRING, _CHAR}


def grep(request: GrepRequest, *, root: Path) -> GrepReport:
    """Text search that can exclude comments/string literals (C.grep of WP03 §3)."""
    pattern = re.compile(request.pattern if request.is_regexp else re.escape(request.pattern))
    matches: list[GrepMatch] = []
    for path in _iter_search_files(root, request.paths):
        matches.extend(_search_file(path, root, pattern, request))
    kept, truncated = cap_list(matches, request.max_results)
    return GrepReport(ok=True, matches=kept, truncated=truncated)


def _iter_search_files(root: Path, paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for entry in paths:
        candidate = root / entry
        if candidate.is_dir():
            files.extend(
                p for p in candidate.rglob("*") if p.is_file() and p.suffix in _SOURCE_SUFFIXES
            )
        elif candidate.is_file():
            files.append(candidate)
        else:
            files.extend(p for p in root.glob(entry) if p.is_file())
    return files


def _search_file(
    path: Path, root: Path, pattern: re.Pattern[str], request: GrepRequest
) -> list[GrepMatch]:
    text = path.read_text(encoding="utf-8", errors="replace")
    exclude = request.exclude_comments or request.exclude_strings
    categories = _classify(text) if exclude else None
    line_starts = _line_start_offsets(text)
    lines = text.splitlines()
    results: list[GrepMatch] = []
    for match in pattern.finditer(text):
        if categories is not None and _is_excluded(
            categories[match.start()], request.exclude_comments, request.exclude_strings
        ):
            continue
        line_no = bisect_right(line_starts, match.start())
        before, after = extract_context(lines, line_no, request.context_lines)
        results.append(
            GrepMatch(
                file=to_relative(path, root),
                line=line_no,
                text=lines[line_no - 1],
                context_before=before,
                context_after=after,
            )
        )
    return results


def _is_excluded(category: int, exclude_comments: bool, exclude_strings: bool) -> bool:
    if exclude_comments and category in _COMMENT_CATEGORIES:
        return True
    return exclude_strings and category in _STRING_CATEGORIES


def _line_start_offsets(text: str) -> list[int]:
    starts = [0]
    for i, char in enumerate(text):
        if char == "\n":
            starts.append(i + 1)
    return starts


def _classify(text: str) -> list[int]:
    """Per-character category: code / line comment / block comment / string / char literal."""
    categories = [_CODE] * len(text)
    n = len(text)
    state = _CODE
    i = 0
    while i < n:
        char = text[i]
        if state == _LINE_COMMENT:
            categories[i] = _LINE_COMMENT
            if char == "\n":
                state = _CODE
            i += 1
            continue
        if state == _BLOCK_COMMENT:
            categories[i] = _BLOCK_COMMENT
            if char == "*" and i + 1 < n and text[i + 1] == "/":
                categories[i + 1] = _BLOCK_COMMENT
                state = _CODE
                i += 2
                continue
            i += 1
            continue
        if state in _STRING_CATEGORIES:
            categories[i] = state
            if char == "\\" and i + 1 < n:
                categories[i + 1] = state
                i += 2
                continue
            if (state == _STRING and char == '"') or (state == _CHAR and char == "'"):
                state = _CODE
            i += 1
            continue
        # state == _CODE
        if char == "/" and i + 1 < n and text[i + 1] == "/":
            state = _LINE_COMMENT
            categories[i] = _LINE_COMMENT
            i += 1
            continue
        if char == "/" and i + 1 < n and text[i + 1] == "*":
            state = _BLOCK_COMMENT
            categories[i] = _BLOCK_COMMENT
            i += 1
            continue
        if char == '"':
            state = _STRING
            categories[i] = _STRING
            i += 1
            continue
        if char == "'":
            state = _CHAR
            categories[i] = _CHAR
            i += 1
            continue
        i += 1
    return categories
