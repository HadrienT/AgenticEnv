from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.grep import grep as run_grep
from codeintel.schemas import GrepRequest

from codeintel_mcp.tools.dispatch import dispatch


def grep(
    root: str,
    pattern: str,
    paths: list[str] | None = None,
    exclude_comments: bool = True,
    exclude_strings: bool = True,
    context_lines: int = 0,
    max_results: int = 100,
    is_regexp: bool = False,
) -> dict[str, Any]:
    """Text search that excludes comments/string literals by default (never the sole tool: prefer

    `code.find_symbol`/`code.references` for symbol questions).
    """

    def _run(timeout_s: int) -> dict[str, Any]:
        report = run_grep(
            GrepRequest(
                pattern=pattern,
                paths=paths or ["."],
                exclude_comments=exclude_comments,
                exclude_strings=exclude_strings,
                context_lines=context_lines,
                max_results=max_results,
                is_regexp=is_regexp,
            ),
            root=Path(root),
        )
        return report.model_dump(mode="json")

    return dispatch("code.grep", _run)
