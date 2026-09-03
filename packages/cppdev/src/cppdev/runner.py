from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from corelib.errors import TimeoutError_


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int


def run_command(
    args: Sequence[str],
    *,
    cwd: Path,
    timeout_s: int,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    """Runs `args` with a hard timeout; never `shell=True` (SEC3), never silently killed."""
    from time import monotonic

    started = monotonic()
    try:
        completed = subprocess.run(  # noqa: S603 - args is a fixed list, never shell text
            list(args),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((monotonic() - started) * 1000)
        raise TimeoutError_(
            f"command timed out after {timeout_s}s: {args[0]}",
            details={"args": list(args), "timeout_s": timeout_s, "duration_ms": duration_ms},
        ) from exc
    duration_ms = int((monotonic() - started) * 1000)
    return CommandResult(
        args=tuple(args),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_ms=duration_ms,
    )
