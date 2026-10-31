"""Runs one prompt through AgenticEnv as the VS Code bridge would: Docker sandbox, the
`coding` profile, every MCP server. Run with AgenticEnv's interpreter, from ~/AgenticEnv
(corelib resolves .env from the working directory).

usage: drive_agenticenv.py <project> <prompt_file> <out_dir> [--gpu] [--no-mcp]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections import Counter
from pathlib import Path

from openhands.sdk.security.confirmation_policy import NeverConfirm
from openhands_adapter import AgentSession, load_openhands_config
from openhands_adapter.benchmark import copy_back
from openhands_bridge.mcp_catalog import build_mcp_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("prompt_file", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--no-mcp", action="store_true")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    config = load_openhands_config()
    config.sandbox.enable_gpu = args.gpu
    mcp_config, unavailable = ({}, []) if args.no_mcp else build_mcp_config([], config)

    tools: Counter[str] = Counter()
    events_path = args.out_dir / "events.jsonl"
    events = events_path.open("w", encoding="utf-8")

    def on_event(event) -> None:
        name = type(event).__name__
        record = {"t": round(time.time(), 1), "type": name}
        tool = getattr(event, "tool_name", None)
        if name == "ActionEvent" and tool:
            tools[tool] += 1
            record["tool"] = tool
            action = getattr(event, "action", None)
            if action is not None:
                try:
                    record["action"] = action.model_dump(mode="json")
                except Exception:  # noqa: BLE001 - logging only
                    record["action"] = str(action)[:2000]
        elif name == "ObservationEvent":
            observation = getattr(event, "observation", None)
            record["tool"] = tool
            record["text"] = str(getattr(observation, "text", observation))[:3000]
        elif name == "MessageEvent":
            record["text"] = str(event)[:3000]
        events.write(json.dumps(record, default=str) + "\n")
        events.flush()

    started = time.monotonic()
    status, final_text, error, stats = "error", "", None, {}
    container = None
    try:
        with AgentSession(
            oh_config=config,
            confirmation_policy=NeverConfirm(),
            callbacks=[on_event],
            project_path=args.project,
            mcp_config=mcp_config,
            profile="coding",
        ) as session:
            container = session.container_name
            try:
                result = session.send(args.prompt_file.read_text(encoding="utf-8"), blocking=True)
                status, final_text = result.execution_status, result.final_text
            except Exception as exc:  # noqa: BLE001 - keep whatever was edited before the failure
                error = f"{type(exc).__name__}: {exc}"
                status = "timeout_or_error"
            try:
                raw = session.conversation.conversation_stats
                stats = json.loads(raw.model_dump_json()) if hasattr(raw, "model_dump_json") else {}
            except Exception:  # noqa: BLE001 - metrics only
                pass
            assert session.working_copy is not None
            copy_back(session.working_copy, args.project)
    except Exception as exc:  # noqa: BLE001 - recorded, the orchestrator decides
        error = f"{type(exc).__name__}: {exc}"

    summary = {
        "status": status,
        "error": error,
        "final_text": final_text,
        "duration_s": round(time.monotonic() - started, 1),
        "tool_calls": dict(tools),
        "mcp_unavailable": unavailable,
        "container": container,
        "llm_stats": stats,
    }
    (args.out_dir / "agent_result.json").write_text(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
