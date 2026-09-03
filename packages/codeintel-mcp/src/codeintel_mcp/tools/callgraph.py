from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.callgraph import call_graph as run_call_graph
from codeintel.schemas import CallGraphRequest

from codeintel_mcp.tools.dispatch import dispatch


def _call_graph(
    tool: str,
    direction: str,
    root: str,
    file: str,
    line: int,
    column: int,
    max_depth: int,
    max_results: int,
    build_dir: str,
) -> dict[str, Any]:
    def _run(timeout_s: int) -> dict[str, Any]:
        report = run_call_graph(
            CallGraphRequest(
                file=file,
                line=line,
                column=column,
                direction=direction,
                max_depth=max_depth,
                max_results=max_results,
            ),
            root=Path(root),
            compile_commands_dir=Path(root) / build_dir,
            timeout_s=float(timeout_s),
        )
        return report.model_dump(mode="json")

    return dispatch(tool, _run)


def callers(
    root: str,
    file: str,
    line: int,
    column: int,
    max_depth: int = 2,
    max_results: int = 100,
    build_dir: str = "build/dev",
) -> dict[str, Any]:
    """Who calls the function at `file:line:column`, up to `max_depth` levels."""
    return _call_graph(
        "code.callers", "callers", root, file, line, column, max_depth, max_results, build_dir
    )


def callees(
    root: str,
    file: str,
    line: int,
    column: int,
    max_depth: int = 2,
    max_results: int = 100,
    build_dir: str = "build/dev",
) -> dict[str, Any]:
    """What the function at `file:line:column` calls, up to `max_depth` levels."""
    return _call_graph(
        "code.callees", "callees", root, file, line, column, max_depth, max_results, build_dir
    )
