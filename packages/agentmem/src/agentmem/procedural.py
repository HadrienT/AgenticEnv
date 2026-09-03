"""Procedural memory: Git is the source of truth, `mem.procedures` a queryable cache
(blueprint/03-INTERFACES.md §4, WP07 §3). Agents read via MCP; nobody writes a
procedure via MCP (A7) — the only write path is `sync_from_git`.

Deviation from the blueprint placeholder: procedures are plain YAML files
(`agents/procedures/*.yaml`), not the markdown-with-frontmatter form the WP07
prose also allows — a single deterministic format is simpler to parse and test,
and the blueprint itself says "`.md` (ou `.yaml`)"."""

from __future__ import annotations

from pathlib import Path

import yaml
from corelib.db import session_scope
from corelib.errors import NotFoundError, ValidationError
from corelib.serialization import to_json
from sqlalchemy import text

from agentmem.schemas import Procedure, ProcedureStep, ProcedureSummary, SyncReport

DEFAULT_SOURCE_DIR = "agents/procedures"


def _load_procedure_file(path: Path, *, root: Path) -> Procedure:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValidationError(
            f"procedure file is not a mapping: {path}", details={"path": str(path)}
        )
    try:
        steps = [ProcedureStep(**step) for step in raw["steps"]]
        return Procedure(
            name=raw["name"],
            version=str(raw.get("version", "1")),
            description=raw["description"],
            preconditions=list(raw.get("preconditions", [])),
            steps=steps,
            postconditions=list(raw.get("postconditions", [])),
            tags=list(raw.get("tags", [])),
            source_path=path.relative_to(root).as_posix(),
        )
    except KeyError as exc:
        raise ValidationError(
            f"procedure file missing required field {exc}: {path}", details={"path": str(path)}
        ) from exc


def sync_from_git(root: Path, *, source_dir: str = DEFAULT_SOURCE_DIR) -> SyncReport:
    """Idempotent (A8): re-scans `root/source_dir/*.yaml`, upserts by `(name, version)`,
    and deletes any cached row whose `source_path` is no longer present on disk (A9).
    Per-file parse failures are collected in `errors[]`, they never abort the whole sync."""
    procedures_dir = root / source_dir
    found: list[Procedure] = []
    errors: list[str] = []
    if procedures_dir.is_dir():
        for path in sorted(procedures_dir.glob("*.yaml")):
            try:
                found.append(_load_procedure_file(path, root=root))
            except (ValidationError, yaml.YAMLError) as exc:
                errors.append(f"{path}: {exc}")

    with session_scope() as session:
        for proc in found:
            session.execute(
                text(
                    "INSERT INTO mem.procedures "
                    "(name, version, description, preconditions, postconditions, steps, "
                    " tags, source_path, updated_at) "
                    "VALUES (:name, :version, :description, :preconditions, :postconditions, "
                    " CAST(:steps AS jsonb), :tags, :source_path, now()) "
                    "ON CONFLICT (name, version) DO UPDATE SET "
                    " description = EXCLUDED.description, "
                    " preconditions = EXCLUDED.preconditions, "
                    " postconditions = EXCLUDED.postconditions, "
                    " steps = EXCLUDED.steps, "
                    " tags = EXCLUDED.tags, "
                    " source_path = EXCLUDED.source_path, "
                    " updated_at = now()"
                ),
                {
                    "name": proc.name,
                    "version": proc.version,
                    "description": proc.description,
                    "preconditions": proc.preconditions,
                    "postconditions": proc.postconditions,
                    "steps": to_json([step.model_dump() for step in proc.steps]),
                    "tags": proc.tags,
                    "source_path": proc.source_path,
                },
            )

        known_paths = {proc.source_path for proc in found}
        existing = session.execute(
            text("SELECT name, version, source_path FROM mem.procedures")
        ).all()
        removed = 0
        for row in existing:
            if row.source_path not in known_paths:
                session.execute(
                    text("DELETE FROM mem.procedures WHERE name = :name AND version = :version"),
                    {"name": row.name, "version": row.version},
                )
                removed += 1

    return SyncReport(synced=len(found), removed=removed, errors=errors)


def list_procedures(tags: list[str] | None = None) -> list[ProcedureSummary]:
    sql = "SELECT name, version, description, tags, source_path FROM mem.procedures"
    params: dict[str, object] = {}
    if tags:
        sql += " WHERE tags && CAST(:tags AS text[])"
        params["tags"] = tags
    sql += " ORDER BY name, version"

    with session_scope() as session:
        rows = session.execute(text(sql), params).all()

    return [
        ProcedureSummary(
            name=row.name,
            version=row.version,
            description=row.description,
            tags=list(row.tags or []),
            source_path=row.source_path,
        )
        for row in rows
    ]


def get_procedure(name: str, version: str | None = None) -> Procedure:
    with session_scope() as session:
        if version is not None:
            row = session.execute(
                text(
                    "SELECT name, version, description, preconditions, postconditions, steps, "
                    " tags, source_path FROM mem.procedures "
                    "WHERE name = :name AND version = :version"
                ),
                {"name": name, "version": version},
            ).first()
        else:
            row = session.execute(
                text(
                    "SELECT name, version, description, preconditions, postconditions, steps, "
                    " tags, source_path FROM mem.procedures WHERE name = :name "
                    "ORDER BY version DESC LIMIT 1"
                ),
                {"name": name},
            ).first()

    if row is None:
        raise NotFoundError("procedure not found", details={"name": name, "version": version})

    steps = [ProcedureStep(**step) for step in (row.steps or [])]
    return Procedure(
        name=row.name,
        version=row.version,
        description=row.description,
        preconditions=list(row.preconditions or []),
        steps=steps,
        postconditions=list(row.postconditions or []),
        tags=list(row.tags or []),
        source_path=row.source_path,
    )
