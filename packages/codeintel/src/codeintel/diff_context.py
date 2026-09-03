from __future__ import annotations

import re
import subprocess
from pathlib import Path

from codeintel.client import ClangdClient
from codeintel.errors import ProjectDiscoveryError
from codeintel.index import check_index_status
from codeintel.paths import cap_list
from codeintel.positions import from_lsp_position
from codeintel.schemas import DiffContextReport, DiffContextRequest, ImpactedSymbol, Location
from codeintel.session import resolve_client
from codeintel.symbols import find_enclosing_raw_symbol

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")
_SOURCE_GLOBS = ("*.cpp", "*.cc", "*.cxx", "*.hpp", "*.hh", "*.hxx", "*.h", "*.ipp")


def diff_context(
    request: DiffContextRequest,
    *,
    root: Path,
    compile_commands_dir: Path,
    timeout_s: float,
    client: ClangdClient | None = None,
) -> DiffContextReport:
    """Symbols enclosing every changed line between `base_ref` and `head_ref`, with ref counts."""
    index_info = check_index_status(root, compile_commands_dir)
    changed = _changed_ranges(root, request.base_ref, request.head_ref, timeout_s=timeout_s)
    impacted: list[ImpactedSymbol] = []
    with resolve_client(root, compile_commands_dir, client=client) as session:
        for file, ranges in changed.items():
            path = root / file
            if not path.is_file():
                continue
            uri = session.open_file(path, timeout_s=timeout_s)
            doc_symbols = session.document_symbol(uri, timeout_s=timeout_s)
            seen: set[str] = set()
            for start_line, end_line in ranges:
                for line in range(start_line, end_line + 1):
                    symbol = find_enclosing_raw_symbol(doc_symbols, line - 1, 0)
                    if symbol is None or symbol["name"] in seen:
                        continue
                    seen.add(symbol["name"])
                    sel_start = symbol["selectionRange"]["start"]
                    sel_line, sel_column = from_lsp_position(sel_start)
                    refs = session.references(
                        uri, sel_start["line"], sel_start["character"], timeout_s=timeout_s
                    )
                    impacted.append(
                        ImpactedSymbol(
                            name=symbol["name"],
                            location=Location(file=file, line=sel_line, column=sel_column),
                            references_count=len(refs),
                        )
                    )
    kept, truncated = cap_list(impacted, request.max_results)
    return DiffContextReport(ok=True, impacted=kept, truncated=truncated, index=index_info)


def _run_git(args: list[str], root: Path, timeout_s: float) -> str:
    try:
        result = subprocess.run(  # noqa: S603,S607 - fixed `git` binary, argument list is literal
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=True,
        )
    except FileNotFoundError as exc:
        raise ProjectDiscoveryError("git is not on PATH", details={}) from exc
    except subprocess.CalledProcessError as exc:
        raise ProjectDiscoveryError(
            f"git diff failed: {exc.stderr.strip()}", details={"args": args}
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ProjectDiscoveryError("git diff timed out", details={"args": args}) from exc
    return result.stdout


def _changed_ranges(
    root: Path, base_ref: str, head_ref: str, *, timeout_s: float
) -> dict[str, list[tuple[int, int]]]:
    output = _run_git(
        ["diff", "--unified=0", base_ref, head_ref, "--", *_SOURCE_GLOBS], root, timeout_s
    )
    ranges: dict[str, list[tuple[int, int]]] = {}
    current_file: str | None = None
    for line in output.splitlines():
        if line.startswith("+++ "):
            candidate = line[4:].strip()
            current_file = None if candidate == "/dev/null" else _strip_prefix(candidate)
            continue
        if line.startswith("@@") and current_file is not None:
            match = _HUNK_RE.match(line)
            if match:
                start = int(match.group("start"))
                count = int(match.group("count") or "1")
                if count > 0:
                    ranges.setdefault(current_file, []).append((start, start + count - 1))
    return ranges


def _strip_prefix(path: str) -> str:
    return path[2:] if path.startswith(("a/", "b/")) else path
