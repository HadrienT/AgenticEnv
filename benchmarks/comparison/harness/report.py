#!/usr/bin/env python3
"""Writes results/SUMMARY.md: a run counts only if the agent actually ran.

A run stopped by the subscription limit still gets graded, and scores what the untouched
fixture scores, so it is shown as lost, never compared.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
AGENTS = ("agenticenv", "claude")
LIMIT_MARK = "hit your"


def load(task: str, agent: str) -> dict | None:
    path = RESULTS / task / f"{agent}-r1" / "summary.json"
    summary = json.loads(path.read_text()) if path.exists() else None
    if summary is None or LIMIT_MARK in (summary.get("error") or ""):
        return None
    return summary


def cell(summary: dict | None) -> str:
    if summary is None:
        return "not run"
    grade = summary["grade"]
    return f"{grade['passed']}/{grade['total']} ({summary['duration_s']:.0f}s, {summary['status']})"


def main() -> None:
    tasks = sorted(p.parent.name for p in (ROOT / "tasks").glob("*/task.json"))
    rows = {task: {agent: load(task, agent) for agent in AGENTS} for task in tasks}
    lines = ["| Task | AgenticEnv | Claude Code |", "|---|---|---|"]
    lines += [f"| {t} | {cell(r['agenticenv'])} | {cell(r['claude'])} |" for t, r in rows.items()]
    both = [r for r in rows.values() if all(r.values())]
    totals = {
        a: (sum(r[a]["grade"]["passed"] for r in both), sum(r[a]["grade"]["total"] for r in both))
        for a in AGENTS
    }
    every = [r["agenticenv"] for r in rows.values() if r["agenticenv"]]
    passed = sum(s["grade"]["passed"] for s in every)
    total = sum(s["grade"]["total"] for s in every)
    head = [
        "# Comparison results",
        "",
        f"Tasks run by both agents: {len(both)} of {len(tasks)}.",
        "",
        f"- On those tasks, AgenticEnv {totals['agenticenv'][0]}/{totals['agenticenv'][1]}, "
        f"Claude Code {totals['claude'][0]}/{totals['claude'][1]}.",
        f"- AgenticEnv over all {len(every)} tasks: {passed}/{total}.",
        "",
    ]
    (RESULTS / "SUMMARY.md").write_text("\n".join(head + lines) + "\n")


if __name__ == "__main__":
    main()
