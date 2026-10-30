"""Finds what must not enter the sandbox (WP10 §3)."""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Sequence
from pathlib import Path

_SKIPPED_DIRS = {".git", "node_modules", ".venv"}


def find_secret_paths(root: Path, patterns: Sequence[str]) -> tuple[list[str], list[str]]:
    """`(files, directories)` matching `patterns` by basename, relative to `root`.
    A `!name` pattern keeps a name another pattern would catch. A matched directory
    is not descended into: it gets masked as a whole."""
    keep = [p[1:] for p in patterns if p.startswith("!")]
    hide = [p for p in patterns if not p.startswith("!")]

    def matches(name: str) -> bool:
        kept = any(fnmatch.fnmatch(name, p) for p in keep)
        return not kept and any(fnmatch.fnmatch(name, p) for p in hide)

    files: list[str] = []
    dirs: list[str] = []
    for current, subdirs, names in os.walk(root):
        relative = Path(current).relative_to(root)
        for name in list(subdirs):
            if name in _SKIPPED_DIRS:
                subdirs.remove(name)
            elif matches(name):
                subdirs.remove(name)
                dirs.append(str(relative / name))
        files += [str(relative / name) for name in names if matches(name)]
    return sorted(files), sorted(dirs)
