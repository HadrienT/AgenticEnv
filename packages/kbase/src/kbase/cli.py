"""`kbase` CLI: `ingest`, `reindex`, `stats`, `verify`, `search`, `eval`, `harvest`
(WP04 §10, WP05 §10, WP13, WP18)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from corelib.config import get_settings, repo_root
from corelib.db import session_scope
from corelib.errors import AppError
from pydantic import ValidationError as PydanticValidationError

from kbase.config import IngestionConfig, load_kbase_config
from kbase.evaluation import evaluate, load_queries
from kbase.harvest.http import PoliteClient
from kbase.harvest.runner import HarvestSettings, harvest
from kbase.harvest.schemas import HarvestProfile
from kbase.ingestion import ops
from kbase.ingestion import reindex as reindex_mod
from kbase.ingestion.chunking import Chunker, SectionChunker, StructuralChunker
from kbase.ingestion.parsers.base import Parser
from kbase.ingestion.parsers.markdown import MarkdownParser
from kbase.ingestion.parsers.pdf import PdfParser
from kbase.ingestion.pipeline import ingest as run_ingest
from kbase.retrieval.factory import build_embedder, build_retriever
from kbase.retrieval.query import RetrievalFilters, RetrievalQuery
from kbase.schemas import ChunkPolicy, IngestionRequest


def _build_parsers(config: IngestionConfig) -> list[Parser]:
    root = repo_root()
    return [
        MarkdownParser(),
        PdfParser(
            mineru=root / config.mineru_binary,
            adapter=root / config.mineru_adapter,
            cache_dir=root / config.mineru_cache_dir,
            timeout_s=config.pdf_timeout_s,
        ),
    ]


def _build_chunker(strategy: str) -> Chunker:
    return SectionChunker() if strategy == "section" else StructuralChunker()


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
        strategy="section" if config.chunking.strategy == "section" else "structural",
        min_tokens=config.chunking.min_tokens,
        target_tokens=config.chunking.target_tokens,
        max_tokens=config.chunking.max_tokens,
        overlap_tokens=config.chunking.overlap_tokens,
        keep_equation_with_context=config.chunking.keep_equation_with_context,
        never_split_within=config.chunking.never_split_within,
    )
    embedder = build_embedder(config.embeddings)
    try:
        report = run_ingest(
            request,
            documents_dir=settings.paths.documents_dir,
            parsers=_build_parsers(config.ingestion),
            chunker=_build_chunker(config.chunking.strategy),
            embedder=embedder,
            policy=policy,
            max_file_size_bytes=config.ingestion.max_file_size_mb * 1024 * 1024,
            parse_timeout_s=config.ingestion.parse_timeout_s,
            pdf_max_file_size_bytes=config.ingestion.pdf_max_file_size_mb * 1024 * 1024,
            pdf_timeout_s=config.ingestion.pdf_timeout_s,
            require_page=config.provenance.require_page,
            require_section=config.provenance.require_section,
            drop_section_patterns=config.curation.drop_sections,
            contextual_embeddings=config.embeddings.contextual,
        )
    except AppError as exc:
        print(f"ingestion failed: {exc.code}: {exc.message}")
        return 1
    print(report.model_dump_json(indent=2))
    return 0 if report.status != "failed" else 1


def _cmd_reindex(args: argparse.Namespace) -> int:
    config = load_kbase_config()
    embedder = build_embedder(config.embeddings)
    try:
        with session_scope() as session:
            count = reindex_mod.reindex(
                session,
                model_name=args.model,
                embedder=embedder,
                replace=args.replace,
                contextual=config.embeddings.contextual,
            )
    except AppError as exc:
        print(f"reindex failed: {exc.code}: {exc.message}")
        return 1
    print(f"reindexed {count} chunk(s) with model={args.model}")
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    queries = load_queries(repo_root() / args.queries)
    try:
        report = evaluate(
            build_retriever(load_kbase_config()), queries, args.label, details=args.details
        )
    except AppError as exc:
        print(f"eval failed: {exc.code}: {exc.message}")
        return 1
    output = report.model_dump_json(indent=2)
    if args.output:
        (repo_root() / args.output).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


def _cmd_delete(args: argparse.Namespace) -> int:
    with session_scope() as session:
        deleted = ops.delete_documents(session, args.doc_key)
    missing = sorted(set(args.doc_key) - set(deleted))
    print(f"deleted {len(deleted)} document(s): {', '.join(deleted) or '-'}")
    if missing:
        print(f"not found: {', '.join(missing)}")
    return 0 if not missing else 1


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


def _cmd_search(args: argparse.Namespace) -> int:
    config = load_kbase_config()
    retriever = build_retriever(config)
    query = RetrievalQuery(
        text=args.query,
        k=args.k or config.retrieval.default_k,
        filters=RetrievalFilters(),
        strategy=args.strategy,
        rerank=not args.no_rerank,
    )
    try:
        result = retriever.retrieve(query)
    except AppError as exc:
        print(f"search failed: {exc.code}: {exc.message}")
        return 1
    print(result.model_dump_json(indent=2))
    return 0


def _cmd_harvest(args: argparse.Namespace) -> int:
    root = repo_root()
    config = load_kbase_config().harvest
    profile_path = Path(args.profile)
    if not profile_path.is_absolute():
        profile_path = root / profile_path
    try:
        profile = HarvestProfile.model_validate(
            yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        )
    except (OSError, yaml.YAMLError, PydanticValidationError) as exc:
        print(f"harvest failed: invalid profile {profile_path}: {exc}")
        return 1
    manifest = root / config.manifest
    settings = HarvestSettings(
        documents_dir=get_settings().paths.documents_dir,
        manifest=manifest,
        known_manifests=(manifest, *(root / m for m in config.known_manifests)),
        html_dir=config.html_dir,
        md_dir=config.md_dir,
        page_size=config.page_size,
        min_text_chars=config.min_text_chars,
    )
    client = PoliteClient(
        user_agent=config.user_agent,
        min_interval_s=config.min_interval_s,
        max_attempts=config.max_attempts,
        timeout_s=config.timeout_s,
    )
    try:
        report = harvest(
            profile, client=client, settings=settings, max_new=args.max_new, dry_run=args.dry_run
        )
    except AppError as exc:
        print(f"harvest failed: {exc.code}: {exc.message}")
        return 1
    print(report.model_dump_json(indent=2, exclude={"papers"} if args.summary else None))
    return 0 if report.failed == 0 or report.converted > 0 else 1


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
    reindex_parser.add_argument(
        "--replace", action="store_true", help="Drop other models' vectors once done"
    )
    reindex_parser.set_defaults(func=_cmd_reindex)

    delete_parser = subparsers.add_parser(
        "delete", help="Remove documents and all their chunks, embeddings and equations"
    )
    delete_parser.add_argument("--doc-key", action="append", required=True)
    delete_parser.set_defaults(func=_cmd_delete)

    stats_parser = subparsers.add_parser("stats", help="Print corpus counters")
    stats_parser.set_defaults(func=_cmd_stats)

    verify_parser = subparsers.add_parser("verify", help="Check provenance and consistency")
    verify_parser.set_defaults(func=_cmd_verify)

    search_parser = subparsers.add_parser("search", help="Hybrid retrieval over the kbase")
    search_parser.add_argument("query", help="Free-text query")
    search_parser.add_argument("--k", type=int, default=None)
    search_parser.add_argument(
        "--strategy", choices=["hybrid", "vector", "lexical"], default="hybrid"
    )
    search_parser.add_argument("--no-rerank", action="store_true")
    search_parser.set_defaults(func=_cmd_search)

    eval_parser = subparsers.add_parser("eval", help="Measure search on the reference queries")
    eval_parser.add_argument("--queries", default="benchmarks/retrieval/queries.yaml")
    eval_parser.add_argument("--label", required=True)
    eval_parser.add_argument("--output", help="JSON report, relative to the repo root")
    eval_parser.add_argument("--details", action="store_true", help="Per-query ranks in the report")
    eval_parser.set_defaults(func=_cmd_eval)

    harvest_parser = subparsers.add_parser(
        "harvest", help="Fetch arXiv papers into Markdown and a manifest for `ingest`"
    )
    harvest_parser.add_argument("--profile", required=True, help="configs/harvest/<name>.yaml")
    harvest_parser.add_argument("--max-new", type=int, default=None, help="Cap on new papers")
    harvest_parser.add_argument(
        "--dry-run", action="store_true", help="Query arXiv only: no HTML fetch, no file written"
    )
    harvest_parser.add_argument("--summary", action="store_true", help="Omit per-paper results")
    harvest_parser.set_defaults(func=_cmd_harvest)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_arg_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    sys.exit(args.func(args))
