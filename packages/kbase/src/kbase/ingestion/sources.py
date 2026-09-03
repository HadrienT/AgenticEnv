"""`sources.resolve`: reads `manifest.yaml` and confines every path to `documents_dir`."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from corelib.errors import ValidationError
from corelib.ids import deterministic_key
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from kbase.schemas import DocumentMeta, SourceItem


class _ManifestEntry(BaseModel):
    doc_key: str
    path: str
    title: str
    authors: list[str] = []
    year: int | None = None
    doc_type: str
    topic: str | None = None
    asset_class: str | None = None
    source_url: str | None = None
    license: str | None = None
    sha256: str | None = None
    valid_from: date | None = None
    valid_until: date | None = None


class _Manifest(BaseModel):
    documents: list[_ManifestEntry] = []


def _resolve_confined(raw_path: str, documents_dir: Path) -> Path:
    """Anti path-traversal: `raw_path` must be relative and stay under `documents_dir`."""
    if Path(raw_path).is_absolute() or ".." in Path(raw_path).parts:
        raise ValidationError(
            f"manifest entry path escapes documents_dir: {raw_path}",
            details={"path": raw_path},
        )
    resolved = (documents_dir / raw_path).resolve()
    documents_dir_resolved = documents_dir.resolve()
    if resolved != documents_dir_resolved and documents_dir_resolved not in resolved.parents:
        raise ValidationError(
            f"manifest entry path escapes documents_dir: {raw_path}",
            details={"path": raw_path},
        )
    return resolved


def resolve(manifest_path: Path, documents_dir: Path) -> list[SourceItem]:
    """Loads `manifest.yaml`; every `path` is resolved and confined to `documents_dir`."""
    if not manifest_path.is_file():
        raise ValidationError(
            f"manifest file not found: {manifest_path}", details={"path": str(manifest_path)}
        )
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    try:
        manifest = _Manifest.model_validate(raw)
    except PydanticValidationError as exc:
        raise ValidationError(
            f"invalid manifest {manifest_path}: {exc}", details={"path": str(manifest_path)}
        ) from exc

    items: list[SourceItem] = []
    for entry in manifest.documents:
        resolved_path = _resolve_confined(entry.path, documents_dir)
        meta = DocumentMeta(
            doc_key=entry.doc_key,
            title=entry.title,
            authors=entry.authors,
            year=entry.year,
            doc_type=entry.doc_type,
            source_url=entry.source_url,
            license=entry.license,
            topic=entry.topic,
            asset_class=entry.asset_class,
        )
        items.append(
            SourceItem(
                meta=meta,
                resolved_path=str(resolved_path),
                valid_from=entry.valid_from,
                valid_until=entry.valid_until,
            )
        )
    return items


def resolve_path(raw_path: str, documents_dir: Path) -> list[SourceItem]:
    """`source="path"`: ad hoc single-file ingestion with metadata synthesized from the filename.

    Prefer the manifest for anything entering the real corpus (WP04 §7); this exists for
    quick local iteration only.
    """
    resolved_path = _resolve_confined(raw_path, documents_dir)
    meta = DocumentMeta(
        doc_key=deterministic_key(resolved_path.stem),
        title=resolved_path.stem,
        doc_type="notes",
    )
    return [SourceItem(meta=meta, resolved_path=str(resolved_path))]
