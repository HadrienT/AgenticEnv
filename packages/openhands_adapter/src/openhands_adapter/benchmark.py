"""Measures the agent on real tasks (WP17 §1): without it, nobody can tell whether a
change helped. Each task has a fixture repo and a shell check that decides success,
never the agent's own opinion.

`just bench-agent` runs it headless. It needs Docker and llama-server, and each task
costs minutes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import yaml
from corelib.config import repo_root
from pydantic import BaseModel

from openhands_adapter.session import AgentResult, AgentSession
from openhands_adapter.working_copy import WorkingCopy

_CHECK_TIMEOUT_S = 300


class AgentTask(BaseModel):
    id: str
    category: str
    # Fixture directory under benchmarks/agent/fixtures, copied for each run.
    fixture: str
    prompt: str
    check: str


class TaskOutcome(BaseModel):
    task_id: str
    category: str
    passed: bool
    duration_s: float
    status: str
    error: str | None = None


class BenchmarkReport(BaseModel):
    label: str
    started_at: datetime
    success_rate: float
    outcomes: list[TaskOutcome]


Runner = Callable[[str, Path], AgentResult]


def load_tasks(path: Path) -> list[AgentTask]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [AgentTask.model_validate(entry) for entry in raw["tasks"]]


def _prepare(fixture: Path, workdir: Path) -> Path:
    project = workdir / "project"
    shutil.copytree(fixture, project)
    for args in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["-c", "user.email=b@b", "-c", "user.name=b", "commit", "-qm", "fixture"],
    ):
        subprocess.run(["git", *args], cwd=project, check=True, capture_output=True)
    # The agent-server runs as uid 10001 and only reads this copy.
    subprocess.run(["chmod", "-R", "a+rwX", str(project)], check=True)
    return project


def _check(command: str, project: Path) -> bool:
    try:
        # This interpreter, which has pytest: checks must not depend on the system Python.
        path = f"{Path(sys.executable).parent}:{os.environ['PATH']}"
        result = subprocess.run(
            ["bash", "-c", command],
            cwd=project,
            capture_output=True,
            timeout=_CHECK_TIMEOUT_S,
            env={**os.environ, "PATH": path},
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def copy_back(working_copy: WorkingCopy, project: Path) -> None:
    """Brings the agent's edits out of the sandbox, for the check to see. The bridge
    does this at the end of a turn; here there is no bridge."""
    for status, relpath in working_copy.changed_files():
        target = project / relpath
        content = None if status == "DELETED" else working_copy.read_file(relpath)
        if content is None:
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)


def _default_runner(prompt: str, project: Path) -> AgentResult:
    with AgentSession(project_path=project) as session:
        result = session.send(prompt, blocking=True)
        assert result is not None and session.working_copy is not None
        copy_back(session.working_copy, project)
        return result


def run_benchmark(
    tasks: list[AgentTask], *, fixtures: Path, label: str, runner: Runner = _default_runner
) -> BenchmarkReport:
    started_at = datetime.now(UTC)
    outcomes: list[TaskOutcome] = []
    for task in tasks:
        with tempfile.TemporaryDirectory() as workdir:
            project = _prepare(fixtures / task.fixture, Path(workdir))
            started = time.monotonic()
            status = "error"
            error: str | None = None
            try:
                status = runner(task.prompt, project).execution_status
            except Exception as exc:  # noqa: BLE001 - one failed task must not end the run
                error = f"{type(exc).__name__}: {exc}"
            outcomes.append(
                TaskOutcome(
                    task_id=task.id,
                    category=task.category,
                    passed=error is None and _check(task.check, project),
                    duration_s=round(time.monotonic() - started, 1),
                    status=status,
                    error=error,
                )
            )
    passed = sum(outcome.passed for outcome in outcomes)
    return BenchmarkReport(
        label=label,
        started_at=started_at,
        success_rate=passed / len(outcomes) if outcomes else 0.0,
        outcomes=outcomes,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="bench-agent")
    parser.add_argument("--label", required=True)
    parser.add_argument("--only", help="Run the tasks whose id contains this")
    args = parser.parse_args()

    root = repo_root() / "benchmarks" / "agent"
    tasks = [t for t in load_tasks(root / "tasks.yaml") if not args.only or args.only in t.id]
    report = run_benchmark(tasks, fixtures=root / "fixtures", label=args.label)
    output = root / "results" / f"{report.started_at:%Y-%m-%dT%H%M}-{args.label}.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"success_rate": report.success_rate, "report": str(output)}))
