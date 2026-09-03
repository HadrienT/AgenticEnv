from __future__ import annotations

import shutil
from pathlib import Path

from cppdev.diagnostics import parse_compiler_output
from cppdev.errors import ToolMissingError
from cppdev.runner import run_command
from cppdev.schemas import TidyReport, TidyRequest

_DEFAULT_TIMEOUT_S = 600


def run_tidy(
    request: TidyRequest, *, root: Path, timeout_s: int = _DEFAULT_TIMEOUT_S
) -> TidyReport:
    """`clang-tidy -p <build_dir>` on a curated file set; output reuses the compiler parser."""
    if shutil.which("clang-tidy") is None:
        raise ToolMissingError("clang-tidy not found on PATH", details={"tool": "clang-tidy"})
    args = ["clang-tidy", "-p", request.build_dir]
    if request.checks is not None:
        args.append(f"-checks={request.checks}")
    args += request.paths
    result = run_command(args, cwd=root, timeout_s=timeout_s)
    diagnostics = parse_compiler_output(result.stdout + result.stderr, workspace_root=root)
    return TidyReport(ok=result.returncode == 0, diagnostics=diagnostics)
