from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from codeintel.client import ClangdClient
from codeintel.index import check_index_status
from codeintel.paths import cap_list, to_relative
from codeintel.schemas import (
    RegistryCombination,
    RegistryEntry,
    RegistryMatrixReport,
    RegistryMatrixRequest,
)
from codeintel.session import resolve_client

_SOURCE_SUFFIXES = {".cpp", ".cc", ".cxx"}

# Best-effort: a template-instantiating call typically shows up in clangd's `detail`/`arcana`
# as `name<Arg1, Arg2, ...>(`. This is regex over an *AST node's own debug metadata*, not over
# source text (WP03 §10 bans the latter for registry extraction, not the former) — but the
# exact shape of `detail`/`arcana` for a given clangd version isn't part of the documented
# extension contract, so this heuristic must be validated against the real target repo before
# being trusted in production (see blueprint/wp/WP03-code-intelligence.md §2).
_TEMPLATE_CALL_RE = re.compile(r"\b(?P<name>[A-Za-z_]\w*)\s*<(?P<args>[^<>]+)>\s*\(")


def registry_matrix(
    request: RegistryMatrixRequest,
    *,
    root: Path,
    compile_commands_dir: Path,
    timeout_s: float,
    function_names: Sequence[str],
    template_param_order: Sequence[str],
    expected_combinations: Sequence[RegistryCombination] = (),
    client: ClangdClient | None = None,
) -> RegistryMatrixReport:
    """AST-based (never regex-over-source) extraction of the `(instrument, model, engine)` grid."""
    index_info = check_index_status(root, compile_commands_dir)
    entries: list[RegistryEntry] = []
    with resolve_client(root, compile_commands_dir, client=client) as session:
        for path in _iter_source_files(root, request.paths):
            uri = session.open_file(path, timeout_s=timeout_s)
            tree = session.ast(uri, timeout_s=timeout_s)
            if tree is None:
                continue
            entries.extend(_walk_ast(tree, function_names, template_param_order, path, root))
    missing = [
        combo
        for combo in expected_combinations
        if not any(
            e.instrument == combo.instrument and e.model == combo.model and e.engine == combo.engine
            for e in entries
        )
    ]
    kept, truncated = cap_list(entries, request.max_results)
    return RegistryMatrixReport(
        ok=True,
        entries=kept,
        missing_combinations=missing,
        truncated=truncated,
        index=index_info,
    )


def _iter_source_files(root: Path, paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for entry in paths:
        candidate = root / entry
        if candidate.is_dir():
            files.extend(
                p for p in candidate.rglob("*") if p.is_file() and p.suffix in _SOURCE_SUFFIXES
            )
        elif candidate.is_file() and candidate.suffix in _SOURCE_SUFFIXES:
            files.append(candidate)
    return files


def _walk_ast(
    node: dict[str, Any],
    function_names: Sequence[str],
    template_param_order: Sequence[str],
    path: Path,
    root: Path,
) -> list[RegistryEntry]:
    entries: list[RegistryEntry] = []
    if node.get("kind") == "CallExpr":
        name, args = _match_registration_call(node, function_names)
        if name is not None and len(args) >= len(template_param_order):
            kwargs = dict(zip(template_param_order, args, strict=False))
            line = node.get("range", {}).get("start", {}).get("line", 0) + 1
            entries.append(
                RegistryEntry(
                    instrument=kwargs.get("instrument", "?"),
                    model=kwargs.get("model", "?"),
                    engine=kwargs.get("engine", "?"),
                    adapter=f"{to_relative(path, root)}:{line}",
                )
            )
    for child in node.get("children", []):
        entries.extend(_walk_ast(child, function_names, template_param_order, path, root))
    return entries


def _match_registration_call(
    node: dict[str, Any], function_names: Sequence[str]
) -> tuple[str | None, list[str]]:
    for haystack in (node.get("detail") or "", node.get("arcana") or ""):
        match = _TEMPLATE_CALL_RE.search(haystack)
        if match and match.group("name") in function_names:
            args = [a.strip() for a in match.group("args").split(",")]
            return match.group("name"), args
    template_children = [
        c for c in node.get("children", []) if c.get("role") == "template argument"
    ]
    if template_children:
        callee = _callee_name(node)
        if callee in function_names:
            return callee, [c.get("detail", "?") for c in template_children]
    return None, []


def _callee_name(node: dict[str, Any]) -> str | None:
    detail = node.get("detail")
    if not detail:
        return None
    return detail.split("(")[0].split("<")[0].strip() or None
