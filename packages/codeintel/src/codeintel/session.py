from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from codeintel.client import ClangdClient, ClangdSession


@contextmanager
def resolve_client(
    root: Path, compile_commands_dir: Path, *, client: ClangdClient | None
) -> Iterator[ClangdClient]:
    """Reuses an injected client (unit tests) or opens a real short-lived `clangd` session."""
    if client is not None:
        yield client
        return
    with ClangdSession(root, compile_commands_dir) as session:
        yield session
