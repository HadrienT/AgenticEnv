"""One `qm.run` against a real build: what the CLI and the MCP tool share."""

from __future__ import annotations

from pathlib import Path

from corelib.config import repo_root

from qmharness.config import QmharnessConfig
from qmharness.driver import SubprocessQuantModelingClient, build_fingerprint, find_module_file
from qmharness.loader import discover_golden_files, load_cases
from qmharness.runner import run
from qmharness.schemas import RunMode, RunReport


def run_build(
    root: Path,
    *,
    config: QmharnessConfig,
    mode: RunMode,
    timeout_s: float,
    build_dir: str | None = None,
    preset: str | None = None,
    golden_dir: str | None = None,
) -> RunReport:
    """Goldens live in this repo, next to the harness: `quant-modeling` stays free of it."""
    resolved_build_dir = root / (build_dir or config.build_dir)
    fingerprint = build_fingerprint(root, resolved_build_dir, preset or config.build_preset)
    cases = load_cases(discover_golden_files(repo_root() / (golden_dir or config.golden_dir)))
    client = SubprocessQuantModelingClient(find_module_file(resolved_build_dir), config.api)
    try:
        return run(cases, mode=mode, client=client, fingerprint=fingerprint, timeout_s=timeout_s)
    finally:
        client.close()
