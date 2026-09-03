"""Loads versioned test cases from `benchmarks/golden/*.yaml` (WP09 §6, §10).

A malformed case is a `CaseValidationError`, never silently skipped or ignored.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError as PydanticValidationError

from qmharness.errors import CaseValidationError
from qmharness.schemas import CaseSpec


def load_cases_from_file(path: Path) -> list[CaseSpec]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CaseValidationError(f"invalid YAML in {path}", details={"path": str(path)}) from exc
    if not isinstance(raw, list):
        raise CaseValidationError(
            f"{path} must contain a YAML list of cases", details={"path": str(path)}
        )
    cases: list[CaseSpec] = []
    for index, entry in enumerate(raw):
        try:
            cases.append(CaseSpec.model_validate(entry))
        except PydanticValidationError as exc:
            raise CaseValidationError(
                f"malformed case at index {index} in {path}: {exc}",
                details={"path": str(path), "index": index},
            ) from exc
    return cases


def discover_golden_files(golden_dir: Path) -> list[Path]:
    return sorted(golden_dir.glob("*.yaml"))


def load_cases(paths: list[Path]) -> list[CaseSpec]:
    cases: list[CaseSpec] = []
    for path in paths:
        cases.extend(load_cases_from_file(path))
    return cases
