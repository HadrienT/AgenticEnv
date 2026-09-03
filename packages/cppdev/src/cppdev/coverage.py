from __future__ import annotations

import json
import shutil
from pathlib import Path

from cppdev.errors import ToolMissingError
from cppdev.runner import run_command
from cppdev.schemas import CoverageFile, CoverageReport, CoverageRequest

_DEFAULT_TIMEOUT_S = 1800


def collect_coverage(
    request: CoverageRequest, *, build_dir: Path, root: Path, timeout_s: int = _DEFAULT_TIMEOUT_S
) -> CoverageReport:
    """`gcovr --json-summary`: per-file and aggregate line/function coverage."""
    if shutil.which("gcovr") is None:
        raise ToolMissingError("gcovr not found on PATH", details={"tool": "gcovr"})
    args = ["gcovr", "--root", str(root), "--json-summary", "-", str(build_dir)]
    result = run_command(args, cwd=root, timeout_s=timeout_s)
    try:
        payload = json.loads(result.stdout) if result.stdout else {}
    except json.JSONDecodeError:
        payload = {}

    files = [
        CoverageFile(
            path=entry.get("filename", "?"),
            line_pct=float(entry.get("line_percent", 0.0)),
            function_pct=float(entry.get("function_percent", 0.0)),
        )
        for entry in payload.get("files", [])
    ]
    return CoverageReport(
        ok=result.returncode == 0,
        line_pct=float(payload.get("line_percent", 0.0)),
        function_pct=float(payload.get("function_percent", 0.0)),
        files=files,
    )
