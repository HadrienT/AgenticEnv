from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse


def to_relative(path: str | Path, root: Path) -> str:
    """Renders a path relative to `root` (C7); system/external paths are left absolute."""
    candidate = Path(path)
    if not candidate.is_absolute():
        return str(candidate)
    try:
        return str(candidate.relative_to(root))
    except ValueError:
        return str(candidate)


def to_uri(path: Path) -> str:
    """`file://` URI for an LSP `TextDocumentIdentifier`."""
    return path.resolve().as_uri()


def from_uri(uri: str) -> Path:
    """Inverse of `to_uri`; tolerates the `file://` scheme only (no remote URIs)."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"unsupported URI scheme: {uri}")
    return Path(unquote(parsed.path))


def cap_list[T](items: list[T], max_results: int) -> tuple[list[T], int]:
    """Bounds a result list (C3); returns the kept items and the omitted count."""
    if len(items) <= max_results:
        return items, 0
    return items[:max_results], len(items) - max_results


def extract_context(
    lines: list[str], line_no: int, context_lines: int
) -> tuple[list[str], list[str]]:
    """1-based `line_no`; returns up to `context_lines` of surrounding text (C6), never the file."""
    index = line_no - 1
    before = lines[max(0, index - context_lines) : index]
    after = lines[index + 1 : index + 1 + context_lines]
    return before, after
