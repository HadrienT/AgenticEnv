"""The green build hooks, on a real git repository. No Docker: the hooks are plain scripts."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from corelib.config import repo_root

_HOOKS = "agents/openhands-template/.openhands/hooks"
_GREEN = "refs/agenticenv/green"


def _git(project: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=project, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / "a.cpp").write_text("int a;\n")
    (tmp_path / "notes.md").write_text("notes\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    _git(tmp_path, "update-ref", "refs/agenticenv/baseline", "HEAD")
    return tmp_path


def _hook(script: str, project: Path, payload: dict[str, object]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(repo_root() / _HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "OPENHANDS_PROJECT_DIR": str(project)},
        check=False,
    )


def _ran(project: Path, command: str, exit_code: int = 0) -> None:
    payload = {"tool_input": {"command": command}, "tool_response": {"exit_code": exit_code}}
    assert _hook("record_green_build.sh", project, payload).returncode == 0


def _stop(project: Path) -> subprocess.CompletedProcess:
    return _hook("require_green_build.sh", project, {})


def _green(project: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "-q", "--verify", _GREEN], cwd=project, capture_output=True, text=True
    )
    return result.stdout.strip() or None


@pytest.mark.parametrize(
    "command",
    [
        "make",
        "cd build && make -j8",
        "cmake --build build",
        "make clean && make",
        "g++ -std=c++20 a.cpp -o a && ./a",
        "ninja -C build",
        "python -m pytest tests",
        "ctest --test-dir build",
        "set -o pipefail; make 2>&1 | tail -5",
        "npm test",
        'cd build && CXXFLAGS="-g" make',
    ],
)
def test_a_successful_build_is_recorded(project: Path, command: str) -> None:
    _ran(project, command)
    assert _green(project)


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "grep -n make Makefile",
        "make clean",
        "g++ -std=c++20 -c a.cpp -o a.o",
        "make 2>&1 | tail -5",
        "make; echo done",
        "make || true",
        "cmake ..",
        "cat make.log",
        "echo make",
    ],
)
def test_other_commands_prove_nothing(project: Path, command: str) -> None:
    _ran(project, command)
    assert _green(project) is None


def test_a_failed_build_is_not_recorded(project: Path) -> None:
    _ran(project, "make", exit_code=2)
    assert _green(project) is None


def test_recording_leaves_the_staging_area_alone(project: Path) -> None:
    (project / "a.cpp").write_text("int b;\n")
    (project / "new.cpp").write_text("int c;\n")
    _git(project, "add", "new.cpp")
    staged = _git(project, "diff", "--cached", "--name-only")

    _ran(project, "make")

    assert _git(project, "diff", "--cached", "--name-only") == staged


def test_nothing_changed_may_finish(project: Path) -> None:
    assert _stop(project).returncode == 0


def test_a_change_without_code_may_finish(project: Path) -> None:
    (project / "ANSWERS.md").write_text("42\n")
    assert _stop(project).returncode == 0


def test_code_never_built_may_not_finish(project: Path) -> None:
    (project / "a.cpp").write_text("int b;\n")

    result = _stop(project)

    assert result.returncode == 2
    assert json.loads(result.stdout)["decision"] == "deny"
    assert "a.cpp" in json.loads(result.stdout)["reason"]


def test_code_built_may_finish(project: Path) -> None:
    (project / "a.cpp").write_text("int b;\n")
    _ran(project, "make")
    assert _stop(project).returncode == 0


def test_an_edit_after_the_build_may_not_finish(project: Path) -> None:
    (project / "a.cpp").write_text("int b;\n")
    _ran(project, "make")
    (project / "a.cpp").write_text("int c;\n")
    assert _stop(project).returncode == 2


def test_the_refusals_are_bounded(project: Path) -> None:
    (project / "a.cpp").write_text("int b;\n")
    assert [_stop(project).returncode for _ in range(4)] == [2, 2, 2, 0]


def test_a_new_build_grants_new_refusals(project: Path) -> None:
    (project / "a.cpp").write_text("int b;\n")
    assert [_stop(project).returncode for _ in range(4)][-1] == 0
    _ran(project, "make")
    (project / "a.cpp").write_text("int c;\n")
    assert _stop(project).returncode == 2


def test_outside_a_repository_nothing_is_in_the_way(tmp_path: Path) -> None:
    assert _stop(tmp_path).returncode == 0
    _ran(tmp_path, "make")
