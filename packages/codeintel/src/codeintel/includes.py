from __future__ import annotations

import re
from pathlib import Path

from codeintel.paths import cap_list, to_relative
from codeintel.schemas import IncludesReport, IncludesRequest

# `#include` directives only: unlike code.registry_matrix, no semantic extraction is claimed
# here, so a regex over the directive syntax itself is legitimate (WP03 §10 forbids regex only
# for *registry* extraction, where dispatch is indirect and dynamic).
_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*[<"]([^">]+)[">]')

_SOURCE_SUFFIXES = {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h", ".ipp"}


def build_includes(request: IncludesRequest, *, root: Path) -> IncludesReport:
    """Static `#include` graph, one direction, bounded depth (clangd has no such LSP method)."""
    if request.direction == "includes":
        edges = _bfs_includes(root, request.file, request.max_depth)
    else:
        edges = _bfs_included_by(root, request.file, request.max_depth)
    kept, truncated = cap_list(edges, request.max_results)
    return IncludesReport(
        ok=True, file=request.file, direction=request.direction, edges=kept, truncated=truncated
    )


def _direct_include_targets(file_path: Path) -> list[str]:
    if not file_path.is_file():
        return []
    text = file_path.read_text(encoding="utf-8", errors="replace")
    return [match.group(1) for line in text.splitlines() if (match := _INCLUDE_RE.match(line))]


def _resolve_quoted(root: Path, from_file: Path, target: str) -> Path | None:
    candidate = (from_file.parent / target).resolve()
    if candidate.is_file():
        return candidate
    name = Path(target).name
    for path in root.rglob(name):
        if path.is_file():
            return path
    return None


def _bfs_includes(root: Path, file: str, max_depth: int) -> list[str]:
    start = (root / file).resolve()
    visited = {start}
    frontier = [start]
    edges: list[str] = []
    for _ in range(max(1, max_depth)):
        next_frontier: list[Path] = []
        for current in frontier:
            for target in _direct_include_targets(current):
                resolved = _resolve_quoted(root, current, target)
                edges.append(target if resolved is None else to_relative(resolved, root))
                if resolved is not None and resolved not in visited:
                    visited.add(resolved)
                    next_frontier.append(resolved)
        frontier = next_frontier
        if not frontier:
            break
    return edges


def _project_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and p.suffix in _SOURCE_SUFFIXES]


def _direct_includers(root: Path, target_file: Path) -> list[Path]:
    includers = []
    for candidate in _project_files(root):
        for target in _direct_include_targets(candidate):
            if _resolve_quoted(root, candidate, target) == target_file:
                includers.append(candidate)
                break
    return includers


def _bfs_included_by(root: Path, file: str, max_depth: int) -> list[str]:
    start = (root / file).resolve()
    visited = {start}
    frontier = [start]
    edges: list[str] = []
    for _ in range(max(1, max_depth)):
        next_frontier: list[Path] = []
        for current in frontier:
            for includer in _direct_includers(root, current):
                edges.append(to_relative(includer, root))
                if includer not in visited:
                    visited.add(includer)
                    next_frontier.append(includer)
        frontier = next_frontier
        if not frontier:
            break
    return edges
