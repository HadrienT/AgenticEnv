#!/usr/bin/env python3
"""Reruns the Claude runs lost to the subscription limit, one task at a time.

Added after results/FROZEN.sha256 was recorded: it only calls `run.py run`, and
changes neither the tasks, the prompts nor the grading. A run stopped by the limit
is not a result, so it is retried once the limit has reset.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
LIMIT_MARK = "hit your"
PROBE_EVERY_S = 600
MAX_WAIT_S = 12 * 3600


def limited(task: str) -> bool:
    summary = RESULTS / task / "claude-r1" / "summary.json"
    return not summary.exists() or LIMIT_MARK in (json.loads(summary.read_text()).get("error") or "")


def wait_for_reset() -> None:
    waited = 0
    while waited < MAX_WAIT_S:
        probe = subprocess.run(
            ["claude", "-p", "reply OK", "--model", "haiku"], capture_output=True, text=True
        )
        if probe.returncode == 0 and LIMIT_MARK not in probe.stdout + probe.stderr:
            return
        print(f"limit still active, waited {waited}s", flush=True)
        time.sleep(PROBE_EVERY_S)
        waited += PROBE_EVERY_S
    sys.exit("limit did not reset within 12 hours")


def main() -> None:
    tasks = sorted(p.parent.name for p in (ROOT / "tasks").glob("*/task.json"))
    for task in [t for t in tasks if limited(t)]:
        while True:
            subprocess.run(
                [sys.executable, "harness/run.py", "run", "--agent", "claude", "--only", task],
                cwd=ROOT,
            )
            if not limited(task):
                break
            wait_for_reset()
    print("resume finished", flush=True)


if __name__ == "__main__":
    main()
