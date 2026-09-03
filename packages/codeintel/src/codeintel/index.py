from __future__ import annotations

import json
import time
from pathlib import Path

from corelib.hashing import sha256_file

from codeintel.errors import IndexUnavailableError
from codeintel.schemas import IndexInfo

_META_FILENAME = "agenticenv-index-meta.json"


def _meta_path(compile_commands_dir: Path) -> Path:
    return compile_commands_dir / ".cache" / "clangd" / _META_FILENAME


def _background_index_dir(compile_commands_dir: Path) -> Path:
    return compile_commands_dir / ".cache" / "clangd" / "index"


def check_index_status(root: Path, compile_commands_dir: Path) -> IndexInfo:
    """I3/I4: absent `compile_commands.json` fails loudly; a changed one is flagged, not hidden.

    clangd persists its background index as `.idx` shards under
    `<compile_commands_dir>/.cache/clangd/index/` (I1) and updates it incrementally as files
    change (I2) — this function only tracks whether `compile_commands.json` itself has drifted
    since the index was last known-good, which clangd's own incremental indexer cannot detect
    on our behalf.
    """
    compile_commands_path = compile_commands_dir / "compile_commands.json"
    if not compile_commands_path.is_file():
        raise IndexUnavailableError(
            "no compile_commands.json for this build directory; run cpp.configure first",
            details={"build_dir": str(compile_commands_dir)},
        )
    current_hash = sha256_file(compile_commands_path)
    meta_path = _meta_path(compile_commands_dir)
    stale = False
    warning: str | None = None
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
        previous_hash = meta.get("compile_commands_sha256")
        if previous_hash is not None and previous_hash != current_hash:
            stale = True
            warning = (
                "compile_commands.json changed since the index was last refreshed; "
                "results may not reflect the current source tree until clangd reindexes"
            )
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps({"compile_commands_sha256": current_hash, "checked_at": time.time()}),
        encoding="utf-8",
    )
    if not _background_index_dir(compile_commands_dir).is_dir():
        warning = warning or (
            "no background index found yet; the first call may be slow while clangd builds one"
        )
    return IndexInfo(stale=stale, warning=warning)
