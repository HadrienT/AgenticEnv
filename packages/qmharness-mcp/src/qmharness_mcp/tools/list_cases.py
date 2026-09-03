from __future__ import annotations

from pathlib import Path
from typing import Any

from corelib.config import load_yaml_config
from qmharness.config import QmharnessConfig
from qmharness.loader import discover_golden_files, load_cases

from qmharness_mcp.tools.dispatch import dispatch


def list_cases(root: str, golden_dir: str | None = None) -> dict[str, Any]:
    """Lists every available case by product/family, without running anything (WP09 §7)."""

    def _run(timeout_s: int) -> dict[str, Any]:
        config = load_yaml_config("qmharness.yaml", QmharnessConfig)
        resolved_golden_dir = Path(root) / (golden_dir or config.golden_dir)
        cases = load_cases(discover_golden_files(resolved_golden_dir))
        return {"cases": [case.model_dump(mode="json") for case in cases]}

    return dispatch("qm.list_cases", _run)
