"""What agents asked the knowledge base, and whether they found it (`kbase usage`).

Two sources. The invocation log (`obs.tool_invocations`) holds every `kb.*` call the MCP
server answered, with its arguments, its caller and a summary of its hits. Claude Code
transcripts (`~/.claude/projects/<project>/*.jsonl`) hold the same calls seen from the
agent's side, plus what it did next: a web search right after a weak result is the
clearest sign the base did not have the answer, and arXiv ids it cites that the base
does not hold are papers it quoted from memory.

Whether a search "found" something is read from the cross-encoder's best score, a logit:
calibrated on this corpus, a passage on the asked topic scores about 3 and above, an
off-topic query stays below 0.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

FOUND_SCORE = 3.0
PARTIAL_SCORE = 0.0
# What the agent did within this many tool calls after a search counts as its follow-up.
FOLLOW_UP_CALLS = 8
LOGGED_HITS = 10

_KB_PREFIX = "mcp__kbase__"
_WEB_TOOLS = {"WebSearch", "WebFetch"}
_ARXIV_ID = re.compile(
    r"(?:arxiv(?:\.org/(?:abs|pdf)/|[:\s]\s?)|arXiv:?\s?)(\d{2}(?:0[1-9]|1[0-2])\.\d{4,5})",
    re.IGNORECASE,
)


class Hit(BaseModel):
    rank: int | None = None
    doc_key: str | None = None
    document: str | None = None
    section: str | None = None
    rerank: float | None = None


class KbCall(BaseModel):
    ts: datetime
    source: Literal["server", "transcript"]
    caller: str | None = None
    session: str | None = None
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    status: str = "ok"
    n_results: int | None = None
    hits: list[Hit] = Field(default_factory=list)
    # Transcripts only: what the agent did next.
    web_after: list[str] = Field(default_factory=list)
    opened: list[str] = Field(default_factory=list)

    @property
    def best_score(self) -> float | None:
        scores = [h.rerank for h in self.hits if h.rerank is not None]
        return max(scores) if scores else None

    @property
    def verdict(self) -> str:
        """`found`, `partial`, `miss`, `empty`, `error`, or `-` for a call that is not a
        search; `+web` when the agent went to the web right after."""
        if self.status != "ok":
            label = "error"
        elif self.n_results is None:
            label = "-"
        elif self.n_results == 0:
            label = "empty"
        elif self.best_score is None:
            label = "unscored"
        elif self.best_score >= FOUND_SCORE:
            label = "found"
        elif self.best_score >= PARTIAL_SCORE:
            label = "partial"
        else:
            label = "miss"
        return f"{label} +web" if self.web_after else label


class WebLookup(BaseModel):
    ts: datetime
    session: str
    tool: str
    target: str


class CitedPaper(BaseModel):
    arxiv_id: str
    in_kb: bool
    sessions: list[str]


class UsageReport(BaseModel):
    calls: list[KbCall]
    web: list[WebLookup] = Field(default_factory=list)
    cited: list[CitedPaper] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


def summarize_result(data: Any, provenance: list[str] | None = None) -> dict[str, Any]:
    """A short record of what a `kb.*` call returned: for a search, its hits (document,
    section, rerank score) without their text; otherwise the documents it touched."""
    summary: dict[str, Any] = {}
    results = data.get("results") if isinstance(data, dict) else None
    if isinstance(results, list):
        summary["n_results"] = len(results)
        hits = []
        for item in results[:LOGGED_HITS]:
            citation = item.get("citation") or {}
            scores = item.get("scores") or {}
            hits.append(
                {
                    "rank": item.get("rank"),
                    "doc_key": citation.get("doc_key"),
                    "document": citation.get("document"),
                    "section": citation.get("section_path") or citation.get("section"),
                    "rerank": scores.get("rerank"),
                }
            )
        summary["hits"] = hits
        if isinstance(data, dict) and data.get("warnings"):
            summary["warnings"] = data["warnings"]
    if provenance:
        summary["provenance"] = provenance
    return summary


def _call_from_summary(call: KbCall, summary: dict[str, Any] | None) -> KbCall:
    if not summary:
        return call
    hits = [Hit.model_validate(h) for h in summary.get("hits") or []]
    return call.model_copy(update={"n_results": summary.get("n_results"), "hits": hits})


# --- invocation log ---------------------------------------------------------------------


def load_server_calls(
    session: Session, *, since: datetime | None = None, caller: str | None = None
) -> list[KbCall]:
    """`kb.*` calls the MCP server recorded, oldest first. Calls made before the log kept
    arguments and results (2026-11-15) come back with neither."""
    sql = (
        "SELECT ts, tool, args, status, caller, result FROM obs.tool_invocations "
        "WHERE server = 'kbase' AND (CAST(:since AS timestamptz) IS NULL OR ts >= :since) "
        "AND (CAST(:caller AS text) IS NULL OR caller = :caller) ORDER BY ts"
    )
    rows = session.execute(text(sql), {"since": since, "caller": caller}).mappings()
    calls = []
    for row in rows:
        call = KbCall(
            ts=row["ts"],
            source="server",
            caller=row["caller"],
            tool=row["tool"],
            args=row["args"] or {},
            status=row["status"],
        )
        calls.append(_call_from_summary(call, row["result"]))
    return calls


def known_arxiv_ids(session: Session) -> set[str]:
    """arXiv ids of the documents in the base (from their source URL)."""
    urls = session.execute(
        text("SELECT source_url FROM kb.documents WHERE source_url ILIKE '%arxiv.org%'")
    ).scalars()
    found: set[str] = set()
    for url in urls:
        match = _ARXIV_ID.search(url or "")
        if match:
            found.add(match.group(1))
    return found


# --- Claude Code transcripts ------------------------------------------------------------


def claude_project_dir(project: Path, home: Path | None = None) -> Path:
    """Where Claude Code keeps the transcripts of sessions opened in `project`."""
    base = (home or Path.home()) / ".claude" / "projects"
    return base / str(project.expanduser().resolve()).replace("/", "-")


def _transcript_files(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.jsonl")))
        elif path.suffix == ".jsonl":
            files.append(path)
    return files


def _records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record


def _blocks(record: dict[str, Any]) -> list[dict[str, Any]]:
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _result_payload(content: Any) -> Any:
    """The JSON envelope a `kb.*` tool returned, as Claude Code stored it."""
    if isinstance(content, list):
        content = "".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    if not isinstance(content, str):
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _kb_tool(name: str) -> str:
    """`mcp__kbase__kb_search` -> `kb.search`."""
    short = name.removeprefix(_KB_PREFIX)
    return "kb." + short.removeprefix("kb_").removeprefix("kb.")


class _Use(BaseModel):
    id: str
    name: str
    input: dict[str, Any]
    ts: datetime


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _read_session(
    path: Path,
) -> tuple[list[_Use], dict[str, Any], list[tuple[datetime, str]], str | None]:
    """Tool uses in order, their results by id, the assistant's text and the session's
    working directory."""
    uses: list[_Use] = []
    seen: set[str] = set()
    results: dict[str, Any] = {}
    texts: list[tuple[datetime, str]] = []
    cwd: str | None = None
    for record in _records(path):
        ts = _parse_ts(record.get("timestamp"))
        cwd = cwd or record.get("cwd")
        for block in _blocks(record):
            kind = block.get("type")
            if kind == "tool_use" and ts is not None and block.get("id") not in seen:
                seen.add(str(block.get("id")))
                uses.append(
                    _Use(
                        id=str(block.get("id")),
                        name=str(block.get("name")),
                        input=block.get("input") or {},
                        ts=ts,
                    )
                )
            elif kind == "tool_result":
                results[str(block.get("tool_use_id"))] = block
            elif kind == "text" and ts is not None and record.get("type") == "assistant":
                texts.append((ts, str(block.get("text", ""))))
    return uses, results, texts, cwd


def _web_target(use: _Use) -> str:
    return str(use.input.get("query") or use.input.get("url") or "")


def load_transcripts(
    paths: Iterable[Path], *, since: datetime | None = None, known_arxiv: set[str] | None = None
) -> UsageReport:
    """`kb.*` calls, web lookups and arXiv citations found in Claude Code transcripts."""
    files = _transcript_files(paths)
    calls: list[KbCall] = []
    web: list[WebLookup] = []
    cited: dict[str, set[str]] = {}
    for path in files:
        session = path.stem[:8]
        uses, results, texts, cwd = _read_session(path)
        caller = Path(cwd).name if cwd else None
        for index, use in enumerate(uses):
            if since is not None and use.ts < since:
                continue
            if use.name in _WEB_TOOLS:
                web.append(
                    WebLookup(ts=use.ts, session=session, tool=use.name, target=_web_target(use))
                )
                continue
            if not use.name.startswith(_KB_PREFIX):
                continue
            block = results.get(use.id) or {}
            payload = _result_payload(block.get("content"))
            ok = bool(block) and not block.get("is_error") and isinstance(payload, dict)
            data = payload.get("data") if isinstance(payload, dict) else None
            meta = payload.get("meta") if isinstance(payload, dict) else None
            provenance = meta.get("provenance") if isinstance(meta, dict) else None
            call = _call_from_summary(
                KbCall(
                    ts=use.ts,
                    source="transcript",
                    caller=caller,
                    session=session,
                    tool=_kb_tool(use.name),
                    args=use.input,
                    status="ok" if ok else "error",
                ),
                summarize_result(data, provenance) if ok else None,
            )
            hit_keys = {h.doc_key for h in call.hits if h.doc_key}
            after = uses[index + 1 : index + 1 + FOLLOW_UP_CALLS]
            call.web_after = [_web_target(u) for u in after if u.name in _WEB_TOOLS]
            call.opened = sorted(
                {
                    str(u.input.get("doc_key"))
                    for u in after
                    if u.name.startswith(_KB_PREFIX) and u.input.get("doc_key") in hit_keys
                }
            )
            calls.append(call)
        for ts, body in texts:
            if since is not None and ts < since:
                continue
            for match in _ARXIV_ID.finditer(body):
                cited.setdefault(match.group(1), set()).add(session)
    known = known_arxiv or set()
    return UsageReport(
        calls=sorted(calls, key=lambda c: c.ts),
        web=sorted(web, key=lambda w: w.ts),
        cited=[
            CitedPaper(arxiv_id=arxiv_id, in_kb=arxiv_id in known, sessions=sorted(sessions))
            for arxiv_id, sessions in sorted(cited.items())
        ],
        sources=[str(f) for f in files],
    )


# --- rendering --------------------------------------------------------------------------


def since_days(days: float | None, now: datetime) -> datetime | None:
    return None if days is None else now - timedelta(days=days)


def _query_of(call: KbCall) -> str:
    args = call.args
    if "text" in args:
        filters = [f"{k}={v}" for k, v in args.items() if k in {"collections", "jurisdictions"}]
        return f'"{args["text"]}"' + (f"  [{', '.join(filters)}]" if filters else "")
    shown = {k: v for k, v in args.items() if k not in {"strategy", "rerank"}}
    return ", ".join(f"{k}={v}" for k, v in shown.items()) or "(no arguments logged)"


def render(report: UsageReport, *, hits: int = 3) -> str:
    lines: list[str] = []
    searches = [c for c in report.calls if c.n_results is not None]
    verdicts: dict[str, int] = {}
    for call in searches:
        key = call.verdict.split()[0]
        verdicts[key] = verdicts.get(key, 0) + 1
    lines.append(
        f"{len(report.calls)} kb calls, {len(searches)} searches with results logged"
        + (f" ({', '.join(f'{k}: {v}' for k, v in sorted(verdicts.items()))})" if verdicts else "")
        + f"; found >= {FOUND_SCORE:g}, partial >= {PARTIAL_SCORE:g} (best rerank score)"
    )
    for call in report.calls:
        best = f"{call.best_score:.1f}" if call.best_score is not None else "-"
        where = " ".join(x for x in (call.caller, call.session) if x)
        lines.append("")
        lines.append(
            f"{call.ts:%Y-%m-%d %H:%M}  {where}  {call.tool}  {call.verdict} ({best})  "
            f"{_query_of(call)}"
        )
        for hit in call.hits[:hits]:
            score = f"{hit.rerank:5.1f}" if hit.rerank is not None else "    -"
            section = f"  § {hit.section}" if hit.section else ""
            lines.append(f"    {score}  {hit.document}{section}")
        if call.opened:
            lines.append(f"    then opened: {', '.join(call.opened)}")
        for target in call.web_after:
            lines.append(f"    then on the web: {target}")
    if report.web:
        lines.append("")
        lines.append(f"Web lookups ({len(report.web)}):")
        for lookup in report.web:
            lines.append(
                f"  {lookup.ts:%Y-%m-%d %H:%M}  {lookup.session}  {lookup.tool}: {lookup.target}"
            )
    if report.cited:
        missing = [c for c in report.cited if not c.in_kb]
        lines.append("")
        lines.append(
            f"arXiv papers cited by the agent: {len(report.cited)}, {len(missing)} not in the base"
        )
        for paper in report.cited:
            mark = "in kb  " if paper.in_kb else "MISSING"
            lines.append(f"  {mark}  {paper.arxiv_id}  ({', '.join(paper.sessions)})")
    return "\n".join(lines)
