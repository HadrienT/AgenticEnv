"""`kbase.ingestion.pipeline.ingest`: the sole ingestion entry point.

Idempotent (sha256 dedup), one transaction per document (isolation: a failing
document is recorded in `errors[]`, the run finishes `partial`, others still get
written), `dry_run` skips every write (blueprint/03-INTERFACES.md §3.3,
05-SEQUENCES.md §4, WP04 §8)."""

from __future__ import annotations

import signal
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from corelib.db import session_scope
from corelib.errors import (
    AppError,
    ConfigError,
    DependencyError,
    ErrorDTO,
    LimitExceededError,
    NotFoundError,
    TimeoutError_,
    ValidationError,
)
from corelib.hashing import sha256_file, sha256_obj
from corelib.ids import new_uuid7
from corelib.logging import get_logger
from corelib.serialization import to_json
from corelib.time import utc_now
from sqlalchemy import text

from kbase.embeddings.base import Embedder
from kbase.ingestion import dedup, sources, writer
from kbase.ingestion.chunking import Chunker
from kbase.ingestion.parsers.base import Parser
from kbase.schemas import ChunkPolicy, IngestionReport, IngestionRequest

logger = get_logger(__name__)

# kbase.ingestion -> embedder is a local, transient-failure-prone dependency (07-ERRORS §7).
_EMBEDDER_MAX_ATTEMPTS = 3
_EMBEDDER_RETRY_BASE_DELAY_S = 0.2


@contextmanager
def _parse_timeout(seconds: int) -> Iterator[None]:
    """WP04 §14: bounds parser wall-clock time. POSIX only (`SIGALRM`), main thread only."""

    def _handler(signum: int, frame: object) -> None:
        raise TimeoutError_(f"parsing exceeded {seconds}s", details={"timeout_s": seconds})

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _select_parser(parsers: Sequence[Parser], path: Path) -> Parser:
    for parser in parsers:
        if parser.can_parse(path):
            return parser
    raise ValidationError(f"no parser can handle {path.suffix}", details={"path": str(path)})


def _embed_with_retry(embedder: Embedder, texts: Sequence[str]) -> list[Sequence[float]]:
    last_exc: Exception | None = None
    for attempt in range(_EMBEDDER_MAX_ATTEMPTS):
        try:
            return embedder.embed_documents(texts)
        except Exception as exc:  # retry boundary: any embedder failure is treated as transient
            last_exc = exc
            if attempt < _EMBEDDER_MAX_ATTEMPTS - 1:
                time.sleep(_EMBEDDER_RETRY_BASE_DELAY_S * (2**attempt))
    raise DependencyError(
        f"embedder failed after {_EMBEDDER_MAX_ATTEMPTS} attempts: {last_exc}",
        details={"attempts": _EMBEDDER_MAX_ATTEMPTS},
    ) from last_exc


def ingest(
    request: IngestionRequest,
    *,
    documents_dir: Path,
    parsers: Sequence[Parser],
    chunker: Chunker,
    embedder: Embedder,
    policy: ChunkPolicy,
    max_file_size_bytes: int,
    parse_timeout_s: int,
    require_page: bool,
    require_section: bool,
) -> IngestionReport:
    started_monotonic = time.monotonic()
    run_id = new_uuid7()
    config_sha = sha256_obj(request.model_dump(mode="json"))

    try:
        with session_scope() as session:
            writer.assert_dimension_matches(session, embedder.dim)
            session.execute(
                text(
                    "INSERT INTO kb.ingestion_runs (id, started_at, status, config_sha) "
                    "VALUES (:id, :started_at, 'running', :config_sha)"
                ),
                {"id": run_id, "started_at": utc_now(), "config_sha": config_sha},
            )
    except ConfigError:
        raise
    except Exception as exc:
        raise DependencyError(f"database unavailable: {exc}", details={}) from exc

    if request.source == "manifest":
        items = sources.resolve(Path(request.target), documents_dir)
    else:
        items = sources.resolve_path(request.target, documents_dir)

    documents_seen = len(items)
    documents_ingested = 0
    documents_skipped = 0
    chunks_written = 0
    equations_written = 0
    errors: list[ErrorDTO] = []

    for item in items:
        path = Path(item.resolved_path)
        try:
            if not path.is_file():
                raise NotFoundError(f"source file not found: {path}", details={"path": str(path)})
            file_size = path.stat().st_size
            if file_size > max_file_size_bytes:
                raise LimitExceededError(
                    f"file exceeds max_file_size_bytes ({max_file_size_bytes})",
                    details={"path": str(path), "size": file_size},
                )

            file_sha256 = sha256_file(path)
            with session_scope() as session:
                existing = dedup.already_ingested(session, file_sha256)
            if existing is not None and not request.force_reparse:
                documents_skipped += 1
                continue

            parser = _select_parser(parsers, path)
            with _parse_timeout(parse_timeout_s):
                parsed = parser.parse(path, item.meta)

            chunks = chunker.chunk(parsed, policy)

            if request.dry_run:
                documents_ingested += 1
                chunks_written += len(chunks)
                equations_written += sum(1 for c in chunks if c.kind == "equation")
                continue

            embeddings = _embed_with_retry(embedder, [c.content for c in chunks])

            with session_scope() as session:
                report = writer.upsert(
                    session,
                    parsed,
                    chunks,
                    embeddings,
                    embedder,
                    run_id,
                    file_path=str(path),
                    valid_from=item.valid_from,
                    valid_until=item.valid_until,
                    require_page=require_page,
                    require_section=require_section,
                )
            documents_ingested += 1
            chunks_written += report.chunks_written
            equations_written += report.equations_written
        except AppError as exc:
            logger.error(
                "document ingestion failed",
                extra={"path": str(path), "error_code": exc.code},
            )
            errors.append(exc.to_dto())
            continue

    status: Literal["success", "partial", "failed"]
    if not errors:
        status = "success"
    elif documents_ingested > 0:
        status = "partial"
    else:
        status = "failed"

    with session_scope() as session:
        session.execute(
            text(
                "UPDATE kb.ingestion_runs SET finished_at = :finished_at, status = :status, "
                "documents_seen = :documents_seen, documents_ingested = :documents_ingested, "
                "chunks_written = :chunks_written, errors = CAST(:errors AS jsonb) WHERE id = :id"
            ),
            {
                "finished_at": utc_now(),
                "status": status,
                "documents_seen": documents_seen,
                "documents_ingested": documents_ingested,
                "chunks_written": chunks_written,
                "errors": to_json([e.model_dump(mode="json") for e in errors]),
                "id": run_id,
            },
        )

    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    return IngestionReport(
        run_id=str(run_id),
        documents_seen=documents_seen,
        documents_ingested=documents_ingested,
        documents_skipped=documents_skipped,
        chunks_written=chunks_written,
        equations_written=equations_written,
        errors=errors,
        duration_ms=duration_ms,
        status=status,
    )
