from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kbase.usage import Hit, KbCall

from kbase import usage


def _search_result(scores: list[float]) -> dict[str, Any]:
    return {
        "results": [
            {
                "rank": i + 1,
                "content": "long passage text",
                "citation": {
                    "doc_key": f"doc-{i}",
                    "document": f"Paper {i}",
                    "section_path": "2 Method",
                },
                "scores": {"rerank": s, "fused": 0.1},
            }
            for i, s in enumerate(scores)
        ],
        "warnings": [],
    }


def _line(kind: str, ts: str, blocks: list[dict[str, Any]], **extra: Any) -> str:
    role = "assistant" if kind == "assistant" else "user"
    record = {"type": kind, "timestamp": ts, "message": {"role": role, "content": blocks}}
    record.update(extra)
    return json.dumps(record)


def _use(use_id: str, name: str, inp: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": use_id, "name": name, "input": inp}


def _result(use_id: str, payload: Any) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": use_id,
        "content": [{"type": "text", "text": json.dumps(payload)}],
    }


def _transcript(tmp_path: Path) -> Path:
    envelope = {"ok": True, "data": _search_result([-1.5, -2.0]), "meta": {"provenance": []}}
    lines = [
        _line(
            "assistant",
            "2026-11-10T21:40:00Z",
            [_use("t1", "mcp__kbase__kb_search", {"text": "rough Heston QE", "k": 2})],
            cwd="/home/u/quant-modeling",
        ),
        _line("user", "2026-11-10T21:40:01Z", [_result("t1", envelope)]),
        _line(
            "assistant",
            "2026-11-10T21:40:02Z",
            [_use("t2", "WebSearch", {"query": "rough Heston QE scheme arXiv"})],
        ),
        _line(
            "assistant",
            "2026-11-10T21:41:00Z",
            [{"type": "text", "text": "See arXiv:2102.08164 and arxiv.org/abs/2012.09715."}],
        ),
    ]
    path = tmp_path / "abcdef12-0000.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_summarize_result_keeps_hits_without_their_text() -> None:
    summary = usage.summarize_result(_search_result([5.2, 1.0]), ["doc-0"])
    assert summary["n_results"] == 2
    assert summary["hits"][0] == {
        "rank": 1,
        "doc_key": "doc-0",
        "document": "Paper 0",
        "section": "2 Method",
        "rerank": 5.2,
    }
    assert "content" not in json.dumps(summary)
    assert summary["provenance"] == ["doc-0"]


def test_verdict_follows_the_best_rerank_score() -> None:
    def call(scores: list[float], **kw: Any) -> KbCall:
        hits = [Hit(rank=i, rerank=s) for i, s in enumerate(scores)]
        return KbCall(
            ts=datetime(2026, 11, 15, tzinfo=UTC),
            source="server",
            tool="kb.search",
            n_results=len(hits),
            hits=hits,
            **kw,
        )

    assert call([1.0, 4.0]).verdict == "found"
    assert call([2.0]).verdict == "partial"
    assert call([-0.5]).verdict == "miss"
    assert call([]).verdict == "empty"
    assert call([-0.5], web_after=["q"]).verdict == "miss +web"
    assert call([4.0], status="error").verdict == "error"


def test_transcripts_give_the_search_its_hits_and_the_web_search_after_it(
    tmp_path: Path,
) -> None:
    report = usage.load_transcripts([tmp_path / "missing", _transcript(tmp_path).parent])
    (call,) = report.calls
    assert call.tool == "kb.search"
    assert call.caller == "quant-modeling"
    assert call.session == "abcdef12"
    assert call.args["text"] == "rough Heston QE"
    assert [h.doc_key for h in call.hits] == ["doc-0", "doc-1"]
    assert call.web_after == ["rough Heston QE scheme arXiv"]
    assert call.verdict == "miss +web"
    assert [w.target for w in report.web] == ["rough Heston QE scheme arXiv"]


def test_transcripts_flag_cited_arxiv_papers_the_base_lacks(tmp_path: Path) -> None:
    report = usage.load_transcripts([_transcript(tmp_path)], known_arxiv={"2012.09715"})
    assert {(c.arxiv_id, c.in_kb) for c in report.cited} == {
        ("2102.08164", False),
        ("2012.09715", True),
    }


def test_since_drops_older_calls(tmp_path: Path) -> None:
    report = usage.load_transcripts(
        [_transcript(tmp_path)], since=datetime(2026, 11, 11, tzinfo=UTC)
    )
    assert report.calls == [] and report.cited == []


def test_claude_project_dir_mirrors_claude_codes_naming(tmp_path: Path) -> None:
    project = tmp_path / "quant-modeling"
    project.mkdir()
    expected = str(project.resolve()).replace("/", "-")
    assert usage.claude_project_dir(project, home=tmp_path).name == expected


def test_render_lists_the_query_its_hits_and_the_missing_papers(tmp_path: Path) -> None:
    report = usage.load_transcripts([_transcript(tmp_path)], known_arxiv=set())
    out = usage.render(report, hits=1)
    assert '"rough Heston QE"' in out
    assert "Paper 0" in out and "Paper 1" not in out
    assert "then on the web: rough Heston QE scheme arXiv" in out
    assert "MISSING  2102.08164" in out
