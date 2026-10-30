from __future__ import annotations

from collections.abc import Mapping, Sequence
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
_CALL_KINDS = {"CallExpr", "CXXMemberCall", "CXXMemberCallExpr"}
_CALLEE_KINDS = {"Member", "MemberExpr", "DeclRef", "DeclRefExpr"}


def registry_matrix(
    request: RegistryMatrixRequest,
    *,
    root: Path,
    compile_commands_dir: Path,
    timeout_s: float,
    function_names: Sequence[str],
    key_enums: Mapping[str, str],
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
            entries.extend(_walk_ast(tree, function_names, key_enums, path, root))
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
    key_enums: Mapping[str, str],
    path: Path,
    root: Path,
) -> list[RegistryEntry]:
    children = node.get("children") or []
    if node.get("kind") in _CALL_KINDS and any(
        child.get("kind") in _CALLEE_KINDS and child.get("detail") in function_names
        for child in children
    ):
        key = _enumerators(node, key_enums)
        line = node.get("range", {}).get("start", {}).get("line", 0) + 1
        return [
            RegistryEntry(
                instrument=key.get("instrument", "?"),
                model=key.get("model", "?"),
                engine=key.get("engine", "?"),
                adapter=f"{to_relative(path, root)}:{line}",
            )
        ]
    entries: list[RegistryEntry] = []
    for child in children:
        entries.extend(_walk_ast(child, function_names, key_enums, path, root))
    return entries


def _enumerators(node: dict[str, Any], key_enums: Mapping[str, str]) -> dict[str, str]:
    """The registration key, read from the types of the enumerators in the call: the
    `{InstrumentKind::X, ModelKind::Y, EngineKind::Z}` of `r.register_pricer(...)`. The
    first of each kind wins, since the pricing lambda that follows may mention others."""
    found: dict[str, str] = {}
    for child in node.get("children") or []:
        if child.get("kind") in {"DeclRef", "DeclRefExpr"}:
            enum = _enum_name(child)
            if enum is not None and enum in key_enums:
                found.setdefault(key_enums[enum], child.get("detail", "?"))
        for field, value in _enumerators(child, key_enums).items():
            found.setdefault(field, value)
    return found


def _enum_name(node: dict[str, Any]) -> str | None:
    for child in node.get("children") or []:
        if child.get("kind") == "Enum":
            detail = child.get("detail")
            return str(detail) if detail else None
        name = _enum_name(child)
        if name is not None:
            return name
    return None
