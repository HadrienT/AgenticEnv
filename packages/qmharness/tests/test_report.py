from __future__ import annotations

from datetime import UTC, datetime

from qmharness.report import comparison_report_to_markdown, run_report_to_markdown
from qmharness.schemas import (
    BuildFingerprint,
    CaseResult,
    ComparisonCaseDiff,
    ComparisonReport,
    RunReport,
)


def _fingerprint() -> BuildFingerprint:
    return BuildFingerprint(
        commit="abc1234",
        build_preset="release",
        compiler="/usr/bin/c++",
        compiler_version="13.2.0",
        optimization="Release",
        module_path="/tmp/quantmodeling.so",
        module_sha256="0" * 64,
    )


def test_run_report_to_markdown_contains_summary_and_cases() -> None:
    now = datetime.now(UTC)
    report = RunReport(
        run_id="run-1",
        mode="quick",
        started_at=now,
        ended_at=now,
        fingerprint=_fingerprint(),
        results=[
            CaseResult(case_id="c1", family="golden", verdict="pass", message="ok"),
            CaseResult(case_id="c2", family="golden", verdict="fail", message="drift"),
        ],
        summary={"pass": 1, "fail": 1, "warn": 0},
    )
    markdown = run_report_to_markdown(report)
    assert "run-1" in markdown
    assert "c1" in markdown and "c2" in markdown
    assert "1 pass" in markdown or "pass" in markdown


def test_comparison_report_to_markdown_shows_refusal() -> None:
    report = ComparisonReport(comparable=False, refusal_reason="builds differ on: compiler")
    markdown = comparison_report_to_markdown(report)
    assert "REFUSED" in markdown
    assert "compiler" in markdown


def test_comparison_report_to_markdown_shows_diffs() -> None:
    report = ComparisonReport(
        comparable=True,
        diffs=[
            ComparisonCaseDiff(
                case_id="c1",
                baseline_price=1.0,
                candidate_price=1.0001,
                diff_abs=0.0001,
                diff_rel=0.0001,
                verdict="fail",
            )
        ],
        regressions=["c1"],
    )
    markdown = comparison_report_to_markdown(report)
    assert "c1" in markdown
    assert "1 regression" in markdown
