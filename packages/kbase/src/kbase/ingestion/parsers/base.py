"""`Parser` extension point (blueprint/03-INTERFACES.md §3.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from kbase.schemas import DocumentMeta, ParsedDocument


@runtime_checkable
class Parser(Protocol):
    name: str
    version: str

    def can_parse(self, path: Path) -> bool: ...

    def parse(self, path: Path, meta: DocumentMeta) -> ParsedDocument: ...
