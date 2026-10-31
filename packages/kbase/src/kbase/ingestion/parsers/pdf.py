"""`PdfParser`: a PDF, through MinerU, into the Markdown dialect `MarkdownParser` reads.

MinerU lives in its own venv (`.mineru-venv`, heavy and with conflicting dependencies)
and takes minutes per book, so it runs as a subprocess and its result is cached by
content hash: reparsing or resuming an interrupted batch costs nothing. `pipeline` and
forced OCR are deliberate: see `documents/run_mineru_batch.sh`.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from corelib.errors import DependencyError
from corelib.hashing import sha256_file

from kbase.ingestion.parsers.markdown import MarkdownParser
from kbase.schemas import DocumentMeta, ParsedDocument


class PdfParser:
    name = "mineru"
    version = "1"

    def __init__(self, *, mineru: Path, adapter: Path, cache_dir: Path, timeout_s: float) -> None:
        self._mineru = mineru
        self._adapter = adapter
        self._cache_dir = cache_dir
        self._timeout_s = timeout_s
        self._markdown = MarkdownParser()

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path, meta: DocumentMeta) -> ParsedDocument:
        return self._markdown.parse(self._to_markdown(path), meta)

    def _to_markdown(self, path: Path) -> Path:
        cached = self._cache_dir / f"{sha256_file(path)}.md"
        if cached.is_file():
            return cached
        if not self._mineru.is_file():
            raise DependencyError(
                f"MinerU not found: {self._mineru}", details={"path": str(self._mineru)}
            )
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as workdir:
            self._run(
                [str(self._mineru), "-p", str(path), "-o", workdir, "-b", "pipeline", "-m", "ocr"],
                path,
            )
            contents = sorted(Path(workdir).rglob("*_content_list_v2.json"))
            if not contents:
                raise DependencyError(
                    f"MinerU produced no content list for {path.name}",
                    details={"path": str(path)},
                )
            partial = cached.with_suffix(".partial")
            self._run([sys.executable, str(self._adapter), str(contents[0]), str(partial)], path)
            partial.rename(cached)
        return cached

    def _run(self, args: list[str], path: Path) -> None:
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=self._timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise DependencyError(
                f"conversion of {path.name} timed out", details={"path": str(path)}
            ) from exc
        if result.returncode != 0:
            raise DependencyError(
                f"conversion of {path.name} failed: {result.stderr.strip()[-500:]}",
                details={"path": str(path)},
            )
