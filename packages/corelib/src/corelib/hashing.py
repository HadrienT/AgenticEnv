from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Streams the file in chunks; safe for multi-GB GGUF/PDF files."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_obj(obj: Any) -> str:
    """Hashes a JSON-serializable object via a canonical (sorted-key) encoding."""
    encoded = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def args_sha(args: Any) -> str:
    """Alias of `sha256_obj` for tool-invocation argument hashing (corelib.obs)."""
    return sha256_obj(args)
