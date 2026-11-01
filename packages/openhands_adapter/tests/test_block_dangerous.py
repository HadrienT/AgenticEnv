"""The policy hook: a clean rebuild goes through, real work cannot be force-deleted."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from corelib.config import repo_root

_HOOK = "agents/openhands-template/.openhands/hooks/block_dangerous.sh"


def _denied(command: str, hook: Path) -> bool:
    payload = json.dumps({"tool_input": {"command": command}})
    return subprocess.run(["bash", str(hook)], input=payload, text=True).returncode == 2


@pytest.fixture
def hook() -> Path:
    return repo_root() / _HOOK


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf build",
        "rm -rf ./build/",
        "rm -rf build/*",
        "rm -fr dist",
        "rm -rf build dist",
        "rm -rf cmake-build-debug",
        "rm -rf build-asan",
        "cd /workspace/project && rm -rf build && mkdir build && cd build && cmake ..",
        "rm -rf build; cmake -B build",
        "rm -rf node_modules __pycache__",
        "rm -f notes.txt",
        "rm -r scratch",
        "ls -la",
    ],
)
def test_allowed(command: str, hook: Path) -> None:
    assert not _denied(command, hook)


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf src",
        "rm -rf .",
        "rm -rf /",
        "rm -rf ~",
        "rm -rf *",
        "rm -rf ..",
        "rm -rf /build",
        "rm -rf ../build",
        "rm -rf build/../src",
        "rm -rf build src",
        "rm -rf src build",
        "rm -rf build; rm -rf src",
        "rm -rf build && rm -rf src",
        "rm -rf build$(echo /../src)",
        'rm -rf "src"',
        "rm -Rf src",
        "rm -fR src",
        "git push origin main",
        "git reset --hard",
        "cat .ssh/id_rsa",
    ],
)
def test_denied(command: str, hook: Path) -> None:
    assert _denied(command, hook)
