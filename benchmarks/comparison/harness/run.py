#!/usr/bin/env python3
"""Runs tasks against one agent and grades them with the hidden checks.

  run.py run --agent agenticenv|agenticenv-gpu|claude [--only a,b] [--rep N]
  run.py baseline [--only a,b]       every check on the untouched fixture
  run.py grade <run_dir>             grade an existing project again
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"
RESULTS = ROOT / "results"
WORK = Path(os.environ.get("AGX_BENCH_WORK", ROOT / ".work"))
AGX = ROOT.parent.parent
TIMEOUT_S = 1800  # what the `coding` profile allows the local agent
GRADE_TIMEOUT_S = 900


def load_task(task_id: str) -> dict:
    # A plain format, not YAML: the system Python has no yaml and prompts are long.
    path = TASKS / task_id / "task.json"
    task = json.loads(path.read_text())
    task["id"] = task_id
    task["prompt"] = (TASKS / task_id / "prompt.md").read_text()
    return task


def all_tasks() -> list[str]:
    return sorted(p.parent.name for p in TASKS.glob("*/task.json"))


def prepare(task: dict, project: Path) -> None:
    if project.exists():
        shutil.rmtree(project)
    if task.get("base") == "qm":
        qm_prepare(task, project)
    else:
        shutil.copytree(TASKS / task["id"] / "fixture", project)
        for args in (
            ["init", "-q", "-b", "main"],
            ["add", "-A"],
            ["-c", "user.email=b@b", "-c", "user.name=b", "commit", "-qm", "fixture"],
        ):
            subprocess.run(["git", *args], cwd=project, check=True, capture_output=True)
    subprocess.run(["chmod", "-R", "a+rwX", str(project)], check=True)


def qm_sha() -> str:
    return (WORK / "qm-base-sha").read_text().strip()


def qm_restore() -> None:
    """Back to the pristine tree, library rebuilt: the next task must not inherit anything."""
    base = WORK / "qm-base"
    subprocess.run(["git", "reset", "-q", "--hard", qm_sha()], cwd=base, check=True)
    subprocess.run(["git", "clean", "-fdq", "-e", "build"], cwd=base, check=True)
    subprocess.run(["cmake", "--preset", "default"], cwd=base, capture_output=True)
    subprocess.run(["ninja", "-C", "build", "quantModeling"], cwd=base, capture_output=True)


def qm_lock():
    handle = (WORK / "lock-qm").open("w")
    fcntl.flock(handle, fcntl.LOCK_EX)
    return handle


def qm_prepare(task: dict, project: Path) -> None:
    base = WORK / "qm-base"
    lock = qm_lock()
    subprocess.run(["git", "clone", "-q", str(base), str(project)], check=True)
    subprocess.run(["git", "remote", "remove", "origin"], cwd=project, check=True)
    inject = TASKS / task["id"] / "inject.patch"
    subprocess.run(
        ["git", "config", "user.email", "b@b"], cwd=project, check=True, capture_output=True
    )
    subprocess.run(["git", "config", "user.name", "b"], cwd=project, check=True, capture_output=True)
    if inject.exists():
        subprocess.run(["git", "apply", str(inject)], cwd=project, check=True)
        subprocess.run(["git", "commit", "-qam", "wip"], cwd=project, check=True)
    # As on the maintainer's disk: the working tree comes with its build directory.
    subprocess.run(["cp", "-a", "--reflink=auto", str(base / "build"), str(project / "build")], check=True)
    lock.close()


def qm_inplace(task: dict) -> Path:
    """Claude Code runs in a checkout like a developer does: cmake's cache only works at the
    path it was generated for. The caller holds the qm lock."""
    base = WORK / "qm-base"
    inject = TASKS / task["id"] / "inject.patch"
    if inject.exists():
        subprocess.run(["git", "apply", str(inject)], cwd=base, check=True)
        subprocess.run(["git", "-c", "user.email=b@b", "-c", "user.name=b", "commit", "-qam", "wip"], cwd=base, check=True)
    return base


def run_claude(prompt: str, project: Path, out: Path) -> dict:
    started = time.monotonic()
    cmd = [
        "claude", "-p", prompt, "--output-format", "json", "--permission-mode", "acceptEdits",
        "--allowedTools", "Bash,Read,Edit,Write,Glob,Grep",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=project, capture_output=True, text=True, timeout=TIMEOUT_S,
            env={**os.environ, "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"},
        )
        (out / "claude_raw.json").write_text(proc.stdout)
        data = json.loads(proc.stdout)
        return {
            "status": "error" if data.get("is_error") else "finished",
            "error": None if not data.get("is_error") else str(data.get("result"))[:500],
            "final_text": data.get("result", ""),
            "duration_s": round(time.monotonic() - started, 1),
            "turns": data.get("num_turns"),
            "usd_equivalent": data.get("total_cost_usd"),
            "usage": data.get("usage"),
            "models": list(data.get("modelUsage", {})),
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": "timeout", "final_text": "",
                "duration_s": TIMEOUT_S}
    except (json.JSONDecodeError, OSError) as exc:
        return {"status": "error", "error": repr(exc), "final_text": "",
                "duration_s": round(time.monotonic() - started, 1)}


def run_agenticenv(prompt: str, project: Path, out: Path, gpu: bool) -> dict:
    prompt_file = out / "prompt.md"
    prompt_file.write_text(prompt)
    cmd = [
        str(AGX / ".venv/bin/python"), str(ROOT / "harness/drive_agenticenv.py"),
        str(project), str(prompt_file), str(out),
    ]
    if gpu:
        cmd.append("--gpu")
    with (out / "driver.log").open("w") as log:
        try:
            subprocess.run(cmd, cwd=AGX, stdout=log, stderr=subprocess.STDOUT,
                           timeout=TIMEOUT_S + 600)
        except subprocess.TimeoutExpired:
            return {"status": "harness_timeout", "error": "driver timeout", "final_text": "",
                    "duration_s": TIMEOUT_S + 600}
    result = out / "agent_result.json"
    if not result.exists():
        return {"status": "error", "error": "driver crashed", "final_text": "", "duration_s": 0}
    return json.loads(result.read_text())


def killed_by_reaper(result: dict) -> bool:
    """A chat session opening or closing stops every sandbox: not the agent's failure."""
    text = str(result.get("error") or "")
    return result.get("status") != "finished" and any(
        s in text for s in ("Connection refused", "ConnectError", "RemoteProtocolError",
                            "No such container", "Server disconnected")
    )


def grade(task: dict, project: Path, locked: bool = False) -> dict:
    """The check sees a copy, so that grading can never leave anything in the project."""
    hidden = TASKS / task["id"] / "hidden"
    names = task["checks"]
    box = WORK / "grade" / f"{task['id']}-{os.getpid()}"
    shutil.rmtree(box, ignore_errors=True)
    box.mkdir(parents=True)
    try:
        lock_path = WORK / (f"lock-{task['resource']}" if task.get("resource") and not locked else f"lock-none-{os.getpid()}")
        with lock_path.open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            started = time.monotonic()
            try:
                proc = subprocess.run(
                    ["bash", str(hidden / "check.sh"), str(project), str(box), str(hidden)],
                    capture_output=True, text=True, timeout=GRADE_TIMEOUT_S, cwd=box,
                )
                output, code = proc.stdout + proc.stderr, proc.returncode
            except subprocess.TimeoutExpired as exc:
                output = f"{exc.stdout or ''}\nGRADE TIMEOUT"
                code = -1
        passed = set(re.findall(r"^PASS (\S+)", output, re.M))
        failed = set(re.findall(r"^FAIL (\S+)", output, re.M))
        unknown = (passed | failed) - set(names)
        scores = {name: name in passed and name not in failed for name in names}
        return {
            "score": sum(scores.values()) / len(names),
            "passed": sum(scores.values()),
            "total": len(names),
            "checks": scores,
            "unknown_names": sorted(unknown),
            "exit": code,
            "grade_s": round(time.monotonic() - started, 1),
            "output": output[-6000:],
        }
    finally:
        shutil.rmtree(box, ignore_errors=True)


def run_one(task: dict, agent: str, rep: int) -> dict:
    name = f"{agent}-r{rep}"
    out = RESULTS / task["id"] / name
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    project = WORK / "runs" / task["id"] / name
    inplace = task.get("base") == "qm" and agent == "claude"
    lock = None
    if inplace:
        lock = qm_lock()
        project = qm_inplace(task)
    for attempt in range(3):
        if not inplace:
            prepare(task, project)
        if agent == "claude":
            result = run_claude(task["prompt"], project, out)
        else:
            result = run_agenticenv(task["prompt"], project, out, gpu=agent == "agenticenv-gpu")
        result["attempt"] = attempt
        if not killed_by_reaper(result):
            break
    head = subprocess.run(
        ["git", "add", "-AN", "."], cwd=project, capture_output=True, text=True
    )
    diff = subprocess.run(
        ["git", "diff", "HEAD", "--stat", "--", ".", ":(exclude)build"], cwd=project,
        capture_output=True, text=True,
    )
    full = subprocess.run(
        ["git", "diff", "HEAD", "--", ".", ":(exclude)build"], cwd=project, capture_output=True,
        text=True,
    )
    (out / "diff.patch").write_text(full.stdout)
    result["diff_stat"] = diff.stdout[-1500:]
    # Claude Code's in-place run already holds the qm lock.
    result["grade"] = grade(task, project, locked=lock is not None or task.get("resource") != "qm")
    if task.get("base") == "qm" and task.get("resource") == "qm":
        if lock is None:
            lock = qm_lock()
        qm_restore()
    elif inplace:
        qm_restore()
    if lock is not None:
        lock.close()
    (out / "summary.json").write_text(json.dumps(result, indent=1, default=str))
    print(
        f"{task['id']:28} {agent:16} {result['grade']['passed']}/{result['grade']['total']} "
        f"{result['status']} {result['duration_s']}s", flush=True,
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--agent", required=True, choices=["agenticenv", "agenticenv-gpu", "claude"])
    run.add_argument("--only")
    run.add_argument("--rep", type=int, default=1)
    base = sub.add_parser("baseline")
    base.add_argument("--only")
    refc = sub.add_parser("refcheck")
    refc.add_argument("--only")
    again = sub.add_parser("grade")
    again.add_argument("task")
    again.add_argument("run_name")
    args = parser.parse_args()

    WORK.mkdir(exist_ok=True)
    (WORK / "runs").mkdir(exist_ok=True)
    if args.cmd == "grade":
        task = load_task(args.task)
        project = WORK / "runs" / args.task / args.run_name
        summary_path = RESULTS / args.task / args.run_name / "summary.json"
        summary = json.loads(summary_path.read_text())
        summary["grade"] = grade(task, project)
        summary_path.write_text(json.dumps(summary, indent=1, default=str))
        print(args.task, args.run_name, summary["grade"]["passed"], "/", summary["grade"]["total"])
        print(summary["grade"]["output"][-1500:])
        return
    ids = args.only.split(",") if args.only else all_tasks()
    if args.cmd == "refcheck":
        for task_id in ids:
            ref = TASKS / task_id / "ref"
            inject = TASKS / task_id / "inject.patch"
            ref_patch = TASKS / task_id / "ref.patch"
            if not (inject.exists() or ref_patch.exists() or (ref.exists() and any(ref.iterdir()))):
                print(f"{task_id:28} (no reference solution)")
                continue
            task = load_task(task_id)
            project = WORK / "runs" / task_id / "refcheck"
            prepare(task, project)
            if inject.exists():
                subprocess.run(["git", "apply", "-R", str(inject)], cwd=project, check=True)
            elif ref_patch.exists():
                subprocess.run(["git", "apply", str(ref_patch)], cwd=project, check=True)
            else:
                subprocess.run(["cp", "-a", f"{ref}/.", str(project)], check=True)
            graded = grade(task, project)
            if task.get("resource") == "qm":
                qm_restore()
            bad = [k for k, v in graded["checks"].items() if not v]
            print(f"{task_id:28} {graded['passed']}/{graded['total']} {graded['grade_s']}s failing={bad}", flush=True)
            if bad:
                print(graded["output"][-1200:])
            shutil.rmtree(project)
        return
    if args.cmd == "baseline":
        for task_id in ids:
            task = load_task(task_id)
            project = WORK / "runs" / task_id / "baseline"
            prepare(task, project)
            graded = grade(task, project)
            if task.get("resource") == "qm":
                qm_restore()
            print(f"{task_id:28} {graded['passed']}/{graded['total']} exit={graded['exit']} "
                  f"{graded['grade_s']}s unknown={graded['unknown_names']}", flush=True)
            shutil.rmtree(project)
        return
    for task_id in ids:
        task = load_task(task_id)
        run_one(task, args.agent, args.rep)


if __name__ == "__main__":
    main()
