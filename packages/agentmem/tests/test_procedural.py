from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from agentmem.procedural import get_procedure, list_procedures, sync_from_git
from corelib.errors import NotFoundError

pytestmark = pytest.mark.integration


def _write_procedure(root: Path, filename: str, **fields: object) -> None:
    procedures_dir = root / "agents" / "procedures"
    procedures_dir.mkdir(parents=True, exist_ok=True)
    defaults: dict[str, object] = {
        "name": "example-procedure",
        "version": "1",
        "description": "An example procedure.",
        "preconditions": ["p1"],
        "postconditions": ["q1"],
        "tags": ["example"],
        "steps": [{"objective": "do x", "verification": "x is done"}],
    }
    defaults.update(fields)
    (procedures_dir / filename).write_text(yaml.safe_dump(defaults))


def test_sync_from_git_upserts_a_procedure(tmp_path: Path, clean_mem_tables: None) -> None:
    _write_procedure(tmp_path, "example.yaml")

    report = sync_from_git(tmp_path)
    assert report.synced == 1
    assert report.removed == 0
    assert report.errors == []

    procedure = get_procedure("example-procedure")
    assert procedure.description == "An example procedure."
    assert procedure.steps[0].objective == "do x"
    assert procedure.source_path == "agents/procedures/example.yaml"


def test_sync_from_git_is_idempotent(tmp_path: Path, clean_mem_tables: None) -> None:
    _write_procedure(tmp_path, "example.yaml")
    sync_from_git(tmp_path)
    report = sync_from_git(tmp_path)
    assert report.synced == 1
    assert report.removed == 0


def test_sync_from_git_removes_deleted_procedures(tmp_path: Path, clean_mem_tables: None) -> None:
    _write_procedure(tmp_path, "example.yaml")
    sync_from_git(tmp_path)

    (tmp_path / "agents" / "procedures" / "example.yaml").unlink()
    report = sync_from_git(tmp_path)
    assert report.synced == 0
    assert report.removed == 1

    with pytest.raises(NotFoundError):
        get_procedure("example-procedure")


def test_sync_from_git_collects_errors_for_a_malformed_file(
    tmp_path: Path, clean_mem_tables: None
) -> None:
    procedures_dir = tmp_path / "agents" / "procedures"
    procedures_dir.mkdir(parents=True)
    (procedures_dir / "broken.yaml").write_text("name: broken\n")  # missing required fields

    report = sync_from_git(tmp_path)
    assert report.synced == 0
    assert report.errors


def test_list_procedures_filters_by_tags(tmp_path: Path, clean_mem_tables: None) -> None:
    _write_procedure(tmp_path, "a.yaml", name="proc-a", tags=["alpha"])
    _write_procedure(tmp_path, "b.yaml", name="proc-b", tags=["beta"])
    sync_from_git(tmp_path)

    summaries = list_procedures(tags=["alpha"])
    names = {s.name for s in summaries}
    assert "proc-a" in names
    assert "proc-b" not in names


def test_get_procedure_picks_the_latest_version_when_unspecified(
    tmp_path: Path, clean_mem_tables: None
) -> None:
    _write_procedure(tmp_path, "v1.yaml", version="1")
    _write_procedure(tmp_path, "v2.yaml", version="2")
    sync_from_git(tmp_path)

    procedure = get_procedure("example-procedure")
    assert procedure.version == "2"


def test_get_procedure_unknown_raises_not_found(clean_mem_tables: None) -> None:
    with pytest.raises(NotFoundError):
        get_procedure("does-not-exist")
