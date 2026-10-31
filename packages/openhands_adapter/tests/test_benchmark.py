from __future__ import annotations

from pathlib import Path

from corelib.config import repo_root
from openhands_adapter.benchmark import AgentTask, copy_back, load_tasks, run_benchmark
from openhands_adapter.session import AgentResult


def _result() -> AgentResult:
    return AgentResult(
        conversation_id="c", final_text="", execution_status="finished", llm_source="x"
    )


def _task(check: str) -> AgentTask:
    return AgentTask(id="t", category="fix", fixture="repo", prompt="fix it", check=check)


def _fixture(tmp_path: Path) -> Path:
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / "a.txt").write_text("bad\n")
    return tmp_path


def test_success_is_decided_by_the_check_not_the_agent(tmp_path: Path) -> None:
    def fixes(_prompt: str, project: Path) -> AgentResult:
        (project / "a.txt").write_text("good\n")
        return _result()

    report = run_benchmark(
        [_task("grep -q good a.txt")], fixtures=_fixture(tmp_path), label="l", runner=fixes
    )

    assert report.success_rate == 1.0


def test_an_agent_that_claims_success_without_doing_it_fails(tmp_path: Path) -> None:
    report = run_benchmark(
        [_task("grep -q good a.txt")],
        fixtures=_fixture(tmp_path),
        label="l",
        runner=lambda _prompt, _project: _result(),
    )

    assert report.success_rate == 0.0


def test_a_crash_fails_its_task_and_the_run_goes_on(tmp_path: Path) -> None:
    def crash(_prompt: str, _project: Path) -> AgentResult:
        raise RuntimeError("sandbox down")

    report = run_benchmark(
        [_task("true"), _task("true")], fixtures=_fixture(tmp_path), label="l", runner=crash
    )

    assert report.success_rate == 0.0
    assert "sandbox down" in (report.outcomes[0].error or "")


def test_shipped_tasks_load_and_their_fixtures_exist() -> None:
    root = repo_root() / "benchmarks" / "agent"
    tasks = load_tasks(root / "tasks.yaml")

    assert len(tasks) >= 12
    for task in tasks:
        assert (root / "fixtures" / task.fixture).is_dir()


def test_shipped_checks_fail_on_the_untouched_fixture(tmp_path: Path) -> None:
    """A check that passes before the agent does anything measures nothing."""
    root = repo_root() / "benchmarks" / "agent"
    tasks = load_tasks(root / "tasks.yaml")

    report = run_benchmark(
        tasks,
        fixtures=root / "fixtures",
        label="l",
        runner=lambda _prompt, _project: _result(),
    )

    assert [o.task_id for o in report.outcomes if o.passed] == []


def test_copy_back_brings_the_agent_edits_out_of_the_sandbox(tmp_path: Path) -> None:
    class Copy:
        def changed_files(self) -> list[tuple[str, str]]:
            return [("UPDATED", "a.txt"), ("ADDED", "new/b.txt"), ("DELETED", "gone.txt")]

        def read_file(self, relpath: str) -> bytes:
            return relpath.encode()

    (tmp_path / "a.txt").write_text("old")
    (tmp_path / "gone.txt").write_text("old")

    copy_back(Copy(), tmp_path)  # type: ignore[arg-type]

    assert (tmp_path / "a.txt").read_text() == "a.txt"
    assert (tmp_path / "new" / "b.txt").read_text() == "new/b.txt"
    assert not (tmp_path / "gone.txt").exists()
