"""WP08d `WorkingCopy` git bookkeeping, exercised against a real git repo on
the host through a fake `RemoteWorkspace` that shells commands into a temp
dir. No Docker: the point is the git plumbing (technical refs, checkpoints,
diffs), not the sandbox transport.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from openhands_adapter.working_copy import WorkingCopy


@dataclass
class _CmdResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass
class _DownloadResult:
    success: bool


class _FakeWorkspace:
    """Runs `execute_command` as a local shell in `root`; `file_download`
    copies out of it. Mirrors just the `RemoteWorkspace` surface `WorkingCopy`
    touches."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def execute_command(self, command: str, timeout: float = 30.0) -> _CmdResult:
        proc = subprocess.run(
            ["bash", "-c", command],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return _CmdResult(proc.returncode, proc.stdout, proc.stderr)

    def file_download(self, source: str, dest: str) -> _DownloadResult:
        src = Path(source)
        if not src.is_absolute():
            src = self.root / source
        if not src.is_file():
            return _DownloadResult(False)
        shutil.copyfile(src, dest)
        return _DownloadResult(True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    (root / "app.py").write_text("print('v1')\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=root,
        check=True,
    )
    return root


def _wc(repo: Path) -> WorkingCopy:
    wc = WorkingCopy(_FakeWorkspace(repo), str(repo))  # type: ignore[arg-type]
    wc.initialize()
    return wc


def test_initialize_detects_git_repo(repo: Path) -> None:
    assert _wc(repo).is_git is True


def test_initialize_non_git_is_marked(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "note.txt").write_text("hi\n")
    wc = WorkingCopy(_FakeWorkspace(plain), str(plain))  # type: ignore[arg-type]
    wc.initialize()

    assert wc.is_git is False
    assert wc.checkpoint() is None


def test_checkpoint_and_diff_track_agent_edits(repo: Path) -> None:
    wc = _wc(repo)
    (repo / "app.py").write_text("print('v2')\n")
    (repo / "new.py").write_text("x = 1\n")

    checkpoint = wc.checkpoint()

    assert checkpoint is not None
    assert sorted(checkpoint.files) == ["app.py", "new.py"]
    assert "print('v2')" in wc.file_diff("app.py")
    bundle = wc.bundle_diff()
    assert "app.py" in bundle and "new.py" in bundle
    # Technical refs only -- the copy's branch is untouched.
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True, check=True
    )
    assert branch.stdout.strip() == "main"


def test_restore_rolls_the_tree_back_to_baseline(repo: Path) -> None:
    wc = _wc(repo)
    (repo / "app.py").write_text("print('v2')\n")
    checkpoint = wc.checkpoint()
    assert checkpoint is not None
    (repo / "app.py").write_text("print('v3')\n")

    wc.restore(checkpoint.checkpoint_id)

    assert (repo / "app.py").read_text() == "print('v2')\n"


def test_changed_files_reports_agent_edits_by_status(repo: Path) -> None:
    wc = _wc(repo)
    (repo / "app.py").write_text("print('v2')\n")  # UPDATED
    (repo / "new.py").write_text("x = 1\n")  # ADDED

    changes = {p: s for s, p in wc.changed_files()}
    assert changes == {"app.py": "UPDATED", "new.py": "ADDED"}


def test_changed_files_ignores_files_untracked_in_source(tmp_path: Path) -> None:
    """A `*.bak` / `.claude/…` that was already sitting untracked in the source
    at session start is folded into the baseline -- it must NOT show up as an
    agent change (this is the bug where the client flagged `.claude/settings…`)."""
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    (root / "app.py").write_text("v1\n")
    subprocess.run(["git", "add", "app.py"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=root,
        check=True,
    )
    # present but never committed, exactly like the real repo's state
    (root / "notes.bak").write_text("scratch\n")
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.local.json").write_text("{}\n")

    wc = WorkingCopy(_FakeWorkspace(root), str(root))  # type: ignore[arg-type]
    wc.initialize()
    assert wc.changed_files() == []

    (root / "app.py").write_text("v2\n")
    assert wc.changed_files() == [("UPDATED", "app.py")]


def test_read_file_returns_content_then_none(repo: Path) -> None:
    wc = _wc(repo)
    (repo / "app.py").write_text("print('v2')\n")

    assert wc.read_file("app.py") == b"print('v2')\n"
    assert wc.read_file("does-not-exist.py") is None


def test_discard_resets_working_tree(repo: Path) -> None:
    wc = _wc(repo)
    (repo / "app.py").write_text("print('vX')\n")

    wc.discard(None)

    assert (repo / "app.py").read_text() == "print('v1')\n"
