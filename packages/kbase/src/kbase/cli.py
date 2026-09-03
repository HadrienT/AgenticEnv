"""`kbase` CLI: `ingest`, `reindex`, `stats`, `verify` (WP04 §10)."""

from __future__ import annotations

import argparse
import sys

from corelib.config import get_settings
from corelib.db import session_scope
from corelib.errors import AppError

from kbase.config import load_kbase_config
from kbase.embeddings.base import Embedder
from kbase.embeddings.hashing import HashingEmbedder
from kbase.ingestion import ops
from kbase.ingestion import reindex as reindex_mod
from kbase.ingestion.chunking import StructuralChunker
from kbase.ingestion.parsers.base import Parser
from kbase.ingestion.parsers.markdown import MarkdownParser
from kbase.ingestion.pipeline import ingest as run_ingest
from kbase.schemas import ChunkPolicy, IngestionRequest


def _build_embedder(config_dim: int, normalize: bool) -> Embedder:
    return HashingEmbedder(dim=config_dim, normalize=normalize)


def _build_parsers() -> list[Parser]:
    return [MarkdownParser()]


def _cmd_ingest(args: argparse.Namespace) -> int:
    settings = get_settings()
    config = load_kbase_config()
    request = IngestionRequest(
        source=args.source,
        target=args.target,
        force_reparse=args.force_reparse,
        dry_run=args.dry_run,
    )
    policy = ChunkPolicy(
        target_tokens=config.chunking.target_tokens,
        max_tokens=config.chunking.max_tokens,
        overlap_tokens=config.chunking.overlap_tokens,
        keep_equation_with_context=config.chunking.keep_equation_with_context,
        never_split_within=config.chunking.never_split_within,
    )
    embedder = _build_embedder(config.embeddings.dim, config.embeddings.normalize)
    try:
        report = run_ingest(
            request,
            documents_dir=settings.paths.documents_dir,
            parsers=_build_parsers(),
            chunker=StructuralChunker(),
            embedder=embedder,
            policy=policy,
            max_file_size_bytes=config.ingestion.max_file_size_mb * 1024 * 1024,
            parse_timeout_s=config.ingestion.parse_timeout_s,
            require_page=config.provenance.require_page,
            require_section=config.provenance.require_section,
        )
    except AppError as exc:
        print(f"ingestion failed: {exc.code}: {exc.message}")
        return 1
    print(report.model_dump_json(indent=2))
    return 0 if report.status != "failed" else 1


def _cmd_reindex(args: argparse.Namespace) -> int:
    config = load_kbase_config()
    embedder = _build_embedder(config.embeddings.dim, config.embeddings.normalize)
    try:
        with session_scope() as session:
            count = reindex_mod.reindex(session, model_name=args.model, embedder=embedder)
    except AppError as exc:
        print(f"reindex failed: {exc.code}: {exc.message}")
        return 1
    print(f"reindexed {count} chunk(s) with model={args.model}")
    return 0


def _cmd_stats(_args: argparse.Namespace) -> int:
    with session_scope() as session:
        report = ops.stats(session)
    print(report.model_dump_json(indent=2))
    return 0


def _cmd_verify(_args: argparse.Namespace) -> int:
    config = load_kbase_config()
    with session_scope() as session:
        report = ops.verify(
            session,
            expected_dim=config.embeddings.dim,
            model_name=config.embeddings.model_name,
            model_version=config.embeddings.model_version,
            require_section=config.provenance.require_section,
        )
    print(report.model_dump_json(indent=2))
    return 0 if report.ok else 1


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kbase")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest documents into the kbase")
    ingest_parser.add_argument("--source", choices=["manifest", "path"], default="manifest")
    ingest_parser.add_argument("--target", required=True, help="manifest.yaml or file path")
    ingest_parser.add_argument("--force-reparse", action="store_true")
    ingest_parser.add_argument("--dry-run", action="store_true")
    ingest_parser.set_defaults(func=_cmd_ingest)

    reindex_parser = subparsers.add_parser("reindex", help="Re-embed existing chunks")
    reindex_parser.add_argument("--model", required=True)
    reindex_parser.set_defaults(func=_cmd_reindex)

    stats_parser = subparsers.add_parser("stats", help="Print corpus counters")
    stats_parser.set_defaults(func=_cmd_stats)

    verify_parser = subparsers.add_parser("verify", help="Check provenance and consistency")
    verify_parser.set_defaults(func=_cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_arg_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    sys.exit(args.func(args))
