"""The disposable sandbox working copy (WP08d).

`AgentSession` bind-mounts the user's folder READ-ONLY at `/workspace/source`
and the agent works on a full `cp -a` copy at `/workspace/project`. This class
drives the git bookkeeping inside that copy through
`RemoteWorkspace.execute_command` -- a session baseline and per-turn
checkpoints stored on **technical refs** (`refs/agenticenv/*`), never on a
branch, so the copy's `git log`/`git branch` stay clean. The copy is thrown
away with the container; nothing here touches the real repo (that's the
bridge's `apply_changes`, WP08d §3.3).
"""

from __future__ import annotations

import shlex
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from corelib.errors import DependencyError

if TYPE_CHECKING:
    from openhands.sdk.workspace import RemoteWorkspace

_BASELINE_REF = "refs/agenticenv/baseline"
_CHECKPOINT_NS = "refs/agenticenv/checkpoints"

_GIT_IDENTITY_EXPORT = (
    "export GIT_AUTHOR_NAME=agenticenv GIT_AUTHOR_EMAIL=agenticenv@local "
    "GIT_COMMITTER_NAME=agenticenv GIT_COMMITTER_EMAIL=agenticenv@local; "
)


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    files: list[str]


class WorkingCopy:
    def __init__(self, workspace: RemoteWorkspace, root: str) -> None:
        self._ws = workspace
        self._root = root
        self._is_git = False

    @property
    def root(self) -> str:
        return self._root

    @property
    def is_git(self) -> bool:
        return self._is_git

    def _run(self, command: str, timeout: float = 60.0) -> tuple[int, str]:
        result = self._ws.execute_command(
            f"cd {shlex.quote(self._root)} && {command}", timeout=timeout
        )
        return result.exit_code, f"{result.stdout}{result.stderr}"

    def _git(self, args: str, timeout: float = 60.0) -> tuple[int, str]:
        # `export` (not `git -c`, nor a one-shot `VAR=x git ...`) so the identity
        # also reaches the nested `git write-tree`/`commit-tree` further down a
        # chained shell command -- those would otherwise run with no identity.
        return self._run(f"{_GIT_IDENTITY_EXPORT}git {args}", timeout=timeout)

    def initialize(self) -> None:
        """Populate `/workspace/project` from the read-only source and pin the
        session baseline. Idempotent-ish: safe to call once in `__enter__`."""
        code, out = self._run(
            "mkdir -p . && cp -a /workspace/source/. . 2>/dev/null; "
            "test -e .git && echo GIT || echo NOGIT",
            timeout=300.0,
        )
        if code != 0:
            raise DependencyError(f"failed to populate the sandbox working copy: {out.strip()}")
        self._is_git = out.strip().splitlines()[-1] == "GIT"
        if self._is_git:
            self._commit_tree_to_ref(_BASELINE_REF, parent=None)

    def _commit_tree_to_ref(self, ref: str, parent: str | None) -> str:
        """Snapshot the whole working tree into a commit on `ref` without
        touching the branch or the index (`git reset` afterwards)."""
        parent_flag = f"-p {parent} " if parent else ""
        code, out = self._git(
            "add -A && "
            "T=$(git write-tree) && "
            f'C=$(git commit-tree "$T" {parent_flag}-m "agenticenv snapshot") && '
            f'git update-ref {ref} "$C" && '
            "git reset -q && "
            'echo "$C"'
        )
        if code != 0:
            raise DependencyError(f"git snapshot failed: {out.strip()}")
        return out.strip().splitlines()[-1]

    def checkpoint(self) -> Checkpoint | None:
        """Take a pre-turn checkpoint. `None` for a non-git copy (the client's
        `checkpoints` capability then no-ops for this session)."""
        if not self._is_git:
            return None
        cp_id = uuid.uuid4().hex[:12]
        self._commit_tree_to_ref(f"{_CHECKPOINT_NS}/{cp_id}", parent=_BASELINE_REF)
        return Checkpoint(checkpoint_id=cp_id, files=self._changed_paths(_BASELINE_REF))

    def restore(self, checkpoint_id: str) -> None:
        if not self._is_git:
            raise DependencyError("this working copy is not a git repository; cannot restore")
        ref = f"{_CHECKPOINT_NS}/{shlex.quote(checkpoint_id)}"
        code, out = self._git(f"cat-file -e {ref} 2>/dev/null && git read-tree --reset -u {ref}")
        if code != 0:
            raise DependencyError(
                f"unknown or unrestorable checkpoint {checkpoint_id}: {out.strip()}"
            )

    def _changed_paths(self, base: str) -> list[str]:
        code, out = self._git(f"add -A -N && git diff --name-only {base}")
        if code != 0:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]

    def file_diff(self, path: str) -> str:
        if not self._is_git:
            raise DependencyError("this working copy is not a git repository; no diff available")
        code, out = self._git(f"add -A -N && git diff {_BASELINE_REF} -- {shlex.quote(path)}")
        return out if code == 0 else ""

    def bundle_diff(self) -> str:
        if not self._is_git:
            raise DependencyError("this working copy is not a git repository; no diff available")
        code, out = self._git(f"add -A -N && git diff {_BASELINE_REF}")
        return out if code == 0 else ""

    def read_file(self, relpath: str) -> bytes | None:
        """Content of a file in the copy, or None if it no longer exists."""
        remote = f"{self._root.rstrip('/')}/{relpath}"
        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            op = self._ws.file_download(remote, tmp.name)
            if not op.success:
                return None
            return Path(tmp.name).read_bytes()

    def discard(self, relpaths: list[str] | None) -> None:
        if not self._is_git:
            raise DependencyError("this working copy is not a git repository; cannot discard")
        if relpaths:
            spec = " ".join(shlex.quote(p) for p in relpaths)
            self._git(f"checkout {_BASELINE_REF} -- {spec}")
        else:
            self._git(f"read-tree --reset -u {_BASELINE_REF}")
