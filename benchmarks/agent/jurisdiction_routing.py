"""Does the local model use kbase's jurisdictions? (WP21 §7, agent test)

For each question of `jurisdiction-routing.yaml`, a short tool loop against the local
LLM (llama-server, OpenAI-compatible API): the model gets an agent profile's system
prompt and the kbase tools exactly as the MCP server exposes them (names, descriptions,
JSON schemas). Tool calls are executed for real against the knowledge base, up to
`--max-turns`; the final answer is then checked.

Scored per question:
- `routed`: the `kb.search` calls name the `regulation` collection (or not, for a
  quant question) and, together, the expected jurisdictions (one search per market is
  fine; `intl` may be added; for a question that names none, either an unfiltered
  search or at least two jurisdictions);
- `labelled`: the answer names the jurisdiction of each expected rule (EU/CRR,
  UK/PRA, US/CFR, Basel), and says "proposal" when one is expected.

    uv run python benchmarks/agent/jurisdiction_routing.py --profile quant
    uv run python benchmarks/agent/jurisdiction_routing.py --profile research --output r.json

Needs llama-server (`sudo -n systemctl start llama-server.service`), Postgres and the
embedding servers; reads `AGX_KBASE_CONFIG` like every kbase command.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import yaml
from corelib.config import load_yaml_config, repo_root
from kbase_mcp.schemas import McpServerConfig
from kbase_mcp.server import build_server

TOOLS = ("kb.search", "kb.list_topics", "kb.list_documents", "kb.list_paragraphs")
LABELS = {
    "eu": r"\bEU\b|\bUE\b|\bCRR\b|Europ|EMIR|\bEBA\b",
    "uk": r"\bUK\b|\bPRA\b|United Kingdom|Royaume-Uni|British|britannique",
    "us": (
        r"\bUS\b|U\.S\.|\bCFR\b|Federal Reserve|\bCFTC\b|\bSEC\b|Regulation (?:Q|KK)"
        r"|États-Unis|améric"
    ),
    "intl": r"Basel|Bâle|\bBCBS\b",
}


def _profile_prompt(profile: str) -> str:
    raw = yaml.safe_load((repo_root() / f"agents/profiles/{profile}.yaml").read_text())
    parts = [p.strip() for p in str(raw["system_prompt"]).split("+")]
    return "\n\n".join((repo_root() / p).read_text(encoding="utf-8") for p in parts)


def _openai_name(name: str) -> str:
    return name.replace(".", "_")


async def _tool_specs(server: Any) -> list[dict[str, Any]]:
    tools = await server.list_tools()
    return [
        {
            "type": "function",
            "function": {
                "name": _openai_name(t.name),
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in tools
        if t.name in TOOLS
    ]


def _chat(
    url: str, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
) -> dict[str, Any]:
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "tools": tools,
            "temperature": 0.0,
            "max_tokens": 1500,
        }
    ).encode()
    request = urllib.request.Request(
        f"{url}/v1/chat/completions", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=600) as response:  # noqa: S310
        return json.loads(response.read())["choices"][0]["message"]  # type: ignore[no-any-return]


def _result_text(result: Any) -> str:
    content = result[0] if isinstance(result, tuple) else result
    texts = (
        [getattr(c, "text", "") for c in content] if isinstance(content, list) else [str(content)]
    )
    text = "\n".join(t for t in texts if t)
    return text[:12000]  # keep the context of an 8k-32k model in check


def _routed(case: dict[str, Any], calls: list[dict[str, Any]]) -> bool:
    """`calls`: every tool call. A `kb.list_documents` of the regulation collection for
    one jurisdiction counts like a search filtered on it (the model then reads the
    paragraphs with `kb.list_paragraphs`)."""
    searches = [c["arguments"] for c in calls if c["tool"] == "kb.search"]
    searches += [
        {"collections": ["regulation"], "jurisdictions": [c["arguments"]["jurisdiction"]]}
        for c in calls
        if c["tool"] == "kb.list_documents"
        and c["arguments"].get("collection") == "regulation"
        and c["arguments"].get("jurisdiction")
    ]
    regulatory = [s for s in searches if "regulation" in (s.get("collections") or [])]
    if case.get("collection") == "quant":
        return not regulatory
    if not regulatory:
        return False
    expected = set(case.get("jurisdictions") or [])
    if not expected:  # the question names none: an unfiltered search, or several
        got = {j for s in regulatory for j in (s.get("jurisdictions") or [])}
        return any(not s.get("jurisdictions") for s in regulatory) or len(got) >= 2
    if any(not s.get("jurisdictions") for s in regulatory):
        return False
    got = {j for s in regulatory for j in s["jurisdictions"]}
    return expected <= got and got - expected <= {"intl"}


def _labelled(case: dict[str, Any], answer: str) -> bool:
    if case.get("collection") == "quant":
        return True
    wanted = case.get("jurisdictions") or ["intl", "eu", "uk", "us"]
    hits = [j for j in wanted if re.search(LABELS[j], answer)]
    ok = len(hits) == len(wanted) if case.get("jurisdictions") else len(hits) >= 2
    if case.get("proposal"):
        ok = ok and re.search(r"propos", answer, re.IGNORECASE) is not None
    return ok


async def run(args: argparse.Namespace) -> dict[str, Any]:
    server = build_server(load_yaml_config("mcp/kbase.yaml", McpServerConfig))
    tools = await _tool_specs(server)
    by_openai = {_openai_name(t): t for t in TOOLS}
    system = _profile_prompt(args.profile)
    cases = yaml.safe_load(Path(args.cases).read_text(encoding="utf-8"))["cases"]
    rows = []
    for case in cases:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": case["question"]},
        ]
        first_search: dict[str, Any] | None = None
        calls: list[dict[str, Any]] = []
        answer = ""
        started = time.monotonic()
        for _ in range(args.max_turns):
            message = _chat(args.url, args.model, messages, tools)
            tool_calls = message.get("tool_calls") or []
            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": tool_calls,
                }
            )
            if not tool_calls:
                answer = message.get("content") or ""
                break
            for tc in tool_calls:
                name = by_openai.get(tc["function"]["name"], tc["function"]["name"])
                try:
                    arguments = json.loads(tc["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                calls.append({"tool": name, "arguments": arguments})
                if name == "kb.search" and first_search is None:
                    first_search = arguments
                try:
                    output = _result_text(await server.call_tool(name, arguments))
                except Exception as exc:  # a bad call is the model's, report it back
                    output = f"error: {exc}"
                messages.append(
                    {"role": "tool", "tool_call_id": tc.get("id", ""), "content": output}
                )
        else:
            messages.append({"role": "user", "content": "Answer now from what you found."})
            answer = _chat(args.url, args.model, messages, []).get("content") or ""
        row = {
            "id": case["id"],
            "question": case["question"],
            "routed": _routed(case, calls),
            "labelled": _labelled(case, answer),
            "first_search": first_search,
            "calls": calls,
            "answer": answer,
            "seconds": round(time.monotonic() - started, 1),
        }
        rows.append(row)
        print(
            f"{row['id']:28} routed={int(row['routed'])} labelled={int(row['labelled'])} "
            f"jurisdictions={(first_search or {}).get('jurisdictions')} "
            f"collections={(first_search or {}).get('collections')} {row['seconds']}s",
            flush=True,
        )
    return {
        "profile": args.profile,
        "model": args.model,
        "routed": sum(r["routed"] for r in rows),
        "labelled": sum(r["labelled"] for r in rows),
        "cases": len(rows),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", default="quant")
    parser.add_argument(
        "--cases", default=str(Path(__file__).with_name("jurisdiction-routing.yaml"))
    )
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default="local")
    parser.add_argument("--max-turns", type=int, default=4)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = asyncio.run(run(args))
    n = report["cases"]
    print(f"routed {report['routed']}/{n}, labelled {report['labelled']}/{n}")
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
