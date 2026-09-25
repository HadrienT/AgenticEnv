"""Write changed files from the sandbox working copy back into the real host
repo (WP08d `apply_changes`).

Pure and Docker-free: the only I/O against the sandbox is the `read_sandbox`
callable the caller injects (`server.py` wires it to
`workspace.file_download` / `execute_command`). Everything else is local
filesystem work, done by the bridge process -- which runs as the user, so
files land with the right ownership, unlike the uid-10001 agent-server.

Conflict rule (WP08d §3.3 / piège table): NEVER write blindly. The host file's
current hash is compared to what it was at the session baseline (or the last
successful apply); a mismatch is `skipped` unless the caller passes
`force=True` for a deliberate user action.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from openhands_bridge.protocol import GitChangeDTO

# relpath -> content bytes, or None if the file no longer exists in the copy
ReadSandbox = Callable[[str], "bytes | None"]


@dataclass
class ApplyResult:
    applied: list[tuple[str, str]] = field(default_factory=list)  # (relpath, status)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (relpath, reason)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_host_tree(host_root: Path, relpaths: Iterable[str]) -> dict[str, str]:
    """Snapshot the current content hashes of the given host files (missing =
    absent from the map)."""
    out: dict[str, str] = {}
    for rel in relpaths:
        p = host_root / rel
        if p.is_file():
            out[rel] = _sha256(p.read_bytes())
    return out


def _dominant_eol(data: bytes) -> bytes:
    return b"\r\n" if data.count(b"\r\n") > data.count(b"\n") - data.count(b"\r\n") else b"\n"


def _match_host_style(new: bytes, old: bytes) -> bytes:
    """Reproduce the old file's BOM and dominant line ending on the new content
    so an apply never silently reflows CRLF<->LF or drops a BOM."""
    bom = b"\xef\xbb\xbf"
    had_bom = old.startswith(bom)
    body = new[len(bom) :] if new.startswith(bom) else new
    if _dominant_eol(old) == b"\r\n":
        body = body.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    else:
        body = body.replace(b"\r\n", b"\n")
    return (bom + body) if had_bom else body


def _is_within(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def apply_changes(
    *,
    changes: list[GitChangeDTO],
    host_root: Path,
    read_sandbox: ReadSandbox,
    baseline_hashes: dict[str, str],
    only_paths: set[str] | None = None,
    force: bool = False,
) -> tuple[ApplyResult, dict[str, str]]:
    """Returns the outcome and the updated host-hash table (to carry into the
    next apply)."""
    result = ApplyResult()
    hashes = dict(baseline_hashes)

    for change in changes:
        rel = change.path
        if only_paths is not None and rel not in only_paths:
            continue

        target = host_root / rel
        if not _is_within(host_root, target):
            result.skipped.append((rel, "path escapes the workspace"))
            continue

        current = _sha256(target.read_bytes()) if target.is_file() else None
        baseline = baseline_hashes.get(rel)
        conflict = current is not None and current != baseline
        if conflict and not force:
            result.skipped.append((rel, "host file changed since session start"))
            continue

        if change.status == "DELETED":
            if target.is_file():
                target.unlink()
            hashes.pop(rel, None)
            result.applied.append((rel, "DELETED"))
            continue

        content = read_sandbox(rel)
        if content is None:
            result.skipped.append((rel, "no longer present in the sandbox"))
            continue

        if target.is_file():
            content = _match_host_style(content, target.read_bytes())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        hashes[rel] = _sha256(content)
        result.applied.append((rel, change.status))

    return result, hashes
