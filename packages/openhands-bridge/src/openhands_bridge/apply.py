"""Write changed files from the sandbox working copy back into the real host
repo (WP08d, applied automatically at the end of each turn since WP08g).

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

import fnmatch
import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from openhands_bridge.protocol import GitChangeDTO

# relpath -> content bytes, or None if the file no longer exists in the copy
# Paths the agent may not change in the real repo: what runs by itself on the
# user's machine or in CI, and secrets. The agent can edit them in its copy; they
# simply stop there, and the client says so (WP12 §4).
PROTECTED_REASON = "protected path, not written to your repo"
_PROTECTED_GLOBS = (
    ".git/*",
    ".github/workflows/*",
    ".gitlab-ci.yml",
    ".husky/*",
    ".envrc",
    ".env",
    ".env.*",
    ".vscode/tasks.json",
    ".vscode/settings.json",
    ".devcontainer/*",
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
    ".netrc",
    ".pgpass",
    "credentials.json",
    "secrets/*",
    "*/secrets/*",
)

ReadSandbox = Callable[[str], "bytes | None"]
IsExecutable = Callable[[str], bool]


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


def _is_binary(data: bytes) -> bool:
    """Same heuristic as git: a NUL byte near the start."""
    return b"\0" in data[:8000]


def _match_host_style(new: bytes, old: bytes) -> bytes:
    """Reproduce the old file's BOM and dominant line ending on the new content
    so an apply never silently reflows CRLF<->LF or drops a BOM. Binary content
    is left alone: its `\\r\\n` bytes are data, not line endings."""
    if _is_binary(new) or _is_binary(old):
        return new
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


def _prune_empty_parents(host_root: Path, target: Path) -> None:
    """Remove directories a delete left empty, so an undo leaves no trace."""
    root = host_root.resolve()
    parent = target.parent.resolve()
    while parent != root and root in parent.parents and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def is_protected(relpath: str) -> bool:
    name = PurePosixPath(relpath).name
    return any(
        fnmatch.fnmatch(relpath, glob) or fnmatch.fnmatch(name, glob) for glob in _PROTECTED_GLOBS
    )


def _apply_one(
    change: GitChangeDTO,
    *,
    target: Path,
    host_root: Path,
    read_sandbox: ReadSandbox,
    is_executable: IsExecutable | None,
    hashes: dict[str, str],
) -> str | None:
    """Writes one change. Returns the reason it was skipped, or None if applied."""
    rel = change.path
    if change.status == "DELETED":
        if target.is_file():
            target.unlink()
            _prune_empty_parents(host_root, target)
        hashes.pop(rel, None)
        return None

    content = read_sandbox(rel)
    if content is None:
        return "no longer present in the sandbox"

    is_new = not target.is_file()
    if not is_new:
        content = _match_host_style(content, target.read_bytes())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    # An existing file keeps its host mode; only a new one needs the sandbox's.
    if is_new and is_executable is not None and is_executable(rel):
        target.chmod(target.stat().st_mode | 0o111)
    hashes[rel] = _sha256(content)
    return None


def apply_changes(
    *,
    changes: list[GitChangeDTO],
    host_root: Path,
    read_sandbox: ReadSandbox,
    baseline_hashes: dict[str, str],
    only_paths: set[str] | None = None,
    force: bool = False,
    is_executable: IsExecutable | None = None,
) -> tuple[ApplyResult, dict[str, str]]:
    """Returns the outcome and the updated host-hash table (to carry into the
    next apply)."""
    result = ApplyResult()
    hashes = dict(baseline_hashes)

    for change in changes:
        rel = change.path
        if only_paths is not None and rel not in only_paths:
            continue

        if is_protected(rel):
            result.skipped.append((rel, PROTECTED_REASON))
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

        try:
            reason = _apply_one(
                change,
                target=target,
                host_root=host_root,
                read_sandbox=read_sandbox,
                is_executable=is_executable,
                hashes=hashes,
            )
        except OSError as exc:
            reason = f"could not write to the host: {exc.strerror or exc}"
        if reason is None:
            result.applied.append((rel, change.status))
        else:
            result.skipped.append((rel, reason))

    return result, hashes
