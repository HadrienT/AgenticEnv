"""Markdown rendering of `RunReport`/`ComparisonReport`, condensed for an LLM (never a
raw dump, per blueprint/00-PRIMER.md §7's "résultat calculé" discipline). JSON is
already free via pydantic's `.model_dump_json()`."""

from __future__ import annotations

from qmharness.schemas import ComparisonReport, RunReport


def run_report_to_markdown(report: RunReport) -> str:
    lines = [
        f"# qmharness run `{report.run_id}` ({report.mode})",
        "",
        f"- commit: `{report.fingerprint.commit}`",
        f"- preset: `{report.fingerprint.build_preset}`",
        f"- compiler: `{report.fingerprint.compiler}` ({report.fingerprint.compiler_version})",
        f"- module: `{report.fingerprint.module_path}` "
        f"(sha256 `{report.fingerprint.module_sha256[:12]}...`)",
        "",
        f"**Summary**: {report.summary.get('pass', 0)} pass, "
        f"{report.summary.get('fail', 0)} fail, {report.summary.get('warn', 0)} warn",
        "",
        "| case | family | verdict | message |",
        "|---|---|---|---|",
    ]
    for result in report.results:
        lines.append(
            f"| {result.case_id} | {result.family} | {result.verdict} | {result.message} |"
        )
    return "\n".join(lines) + "\n"


def comparison_report_to_markdown(report: ComparisonReport) -> str:
    if not report.comparable:
        return f"# qmharness compare -- REFUSED\n\n{report.refusal_reason}\n"
    lines = [
        "# qmharness compare",
        "",
        f"**{len(report.regressions)} regression(s)** out of {len(report.diffs)} shared case(s)",
        "",
        "| case | baseline | candidate | diff_abs | diff_rel | verdict |",
        "|---|---|---|---|---|---|",
    ]
    for diff in report.diffs:
        lines.append(
            f"| {diff.case_id} | {diff.baseline_price:.10g} | {diff.candidate_price:.10g} | "
            f"{diff.diff_abs:.3e} | {diff.diff_rel:.3e} | {diff.verdict} |"
        )
    return "\n".join(lines) + "\n"
