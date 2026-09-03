from __future__ import annotations

from pathlib import Path

import pytest
from corelib.errors import TimeoutError_
from cppdev.runner import run_command


def test_run_command_raises_timeout_error_and_does_not_hang() -> None:
    with pytest.raises(TimeoutError_):
        run_command(["sleep", "5"], cwd=Path.cwd(), timeout_s=1)


def test_run_command_captures_output_and_return_code() -> None:
    result = run_command(["python3", "-c", "print('ok')"], cwd=Path.cwd(), timeout_s=10)

    assert result.returncode == 0
    assert result.stdout.strip() == "ok"
