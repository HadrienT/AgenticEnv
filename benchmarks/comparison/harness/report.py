#!/usr/bin/env python3
"""Writes results/SUMMARY.md: a run counts only if the agent actually ran.

A run stopped by the subscription limit still gets graded, and scores what the untouched
fixture scores, so it is shown as lost, never compared.

  report.py [agent-rN ...]    the runs to show, by default the first of each agent
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
DEFAULT_RUNS = ("agenticenv-r1", "claude-r1")
LIMIT_MARK = "hit your"


def load(task: str, run: str) -> dict | None:
    path = RESULTS / task / run / "summary.json"
    summary = json.loads(path.read_text()) if path.exists() else None
    if summary is None or LIMIT_MARK in (summary.get("error") or ""):
        return None
    return summary


def cell(summary: dict | None) -> str:
    if summary is None:
        return "not run"
    grade = summary["grade"]
    return f"{grade['passed']}/{grade['total']} ({summary['duration_s']:.0f}s, {summary['status']})"


def score(rows: list[dict], run: str) -> str:
    grades = [row[run]["grade"] for row in rows]
    return f"{sum(g['passed'] for g in grades)}/{sum(g['total'] for g in grades)}"


def main() -> None:
    runs = tuple(sys.argv[1:]) or DEFAULT_RUNS
    tasks = sorted(p.parent.name for p in (ROOT / "tasks").glob("*/task.json"))
    rows = {task: {run: load(task, run) for run in runs} for task in tasks}
    lines = ["| Task | " + " | ".join(runs) + " |", "|---|" + "---|" * len(runs)]
    lines += [f"| {t} | " + " | ".join(cell(r[run]) for run in runs) + " |" for t, r in rows.items()]
    both = [r for r in rows.values() if all(r.values())]
    head = ["# Comparison results", "", f"Tasks in every run: {len(both)} of {len(tasks)}.", ""]
    head += [f"- {run}: {score(both, run)} on those tasks." for run in runs]
    for run in runs:
        done = [r for r in rows.values() if r[run]]
        head.append(f"- {run}: {score(done, run)} over its {len(done)} tasks.")
    (RESULTS / "SUMMARY.md").write_text("\n".join([*head, "", *lines]) + "\n")


if __name__ == "__main__":
    main()
