from __future__ import annotations

from typing import Any

from agentmem.procedural import get_procedure as run_get_procedure

from agentmem_mcp.tools.dispatch import dispatch


def get_procedure(name: str, version: str | None = None) -> dict[str, Any]:
    """Full steps of one procedure, by name (+ optional version, defaults to the latest).
    Example: `get_procedure(name="calibrate-sabr")`."""

    def _run(timeout_s: int) -> tuple[dict[str, Any], dict[str, Any]]:
        procedure = run_get_procedure(name, version=version)
        return procedure.model_dump(mode="json"), {}

    return dispatch("mem.get_procedure", _run)
