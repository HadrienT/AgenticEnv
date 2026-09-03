from __future__ import annotations

import re
import shutil
from pathlib import Path

from cppdev.errors import ToolMissingError
from cppdev.runner import run_command
from cppdev.schemas import FormatReport, FormatRequest, FormatViolation

_DEFAULT_TIMEOUT_S = 60
_VIOLATION_RE = re.compile(r"^(?P<file>[^:]+):\d+:\d+: warning: code should be clang-formatted")


def check_format(
    request: FormatRequest, *, root: Path, timeout_s: int = _DEFAULT_TIMEOUT_S
) -> FormatReport:
    """`clang-format --dry-run -Werror`: never rewrites files, only reports what would change."""
    if shutil.which("clang-format") is None:
        raise ToolMissingError("clang-format not found on PATH", details={"tool": "clang-format"})
    args = ["clang-format", "--dry-run", "-Werror", *request.paths]
    result = run_command(args, cwd=root, timeout_s=timeout_s)

    flagged: set[str] = set()
    for line in result.stderr.splitlines():
        match = _VIOLATION_RE.match(line)
        if match is not None:
            flagged.add(match.group("file"))

    violations = [
        FormatViolation(file=path, would_reformat=True) for path in request.paths if path in flagged
    ]
    return FormatReport(ok=result.returncode == 0, violations=violations)
