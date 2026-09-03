from __future__ import annotations

from datetime import UTC, datetime

from qmharness.compare import compare_builds
from qmharness.schemas import BuildFingerprint, CaseResult, RunReport


def _fingerprint(**overrides: str) -> BuildFingerprint:
    base = dict(
        commit="abc1234",
        build_preset="release",
        compiler="/usr/bin/c++",
        compiler_version="13.2.0",
        optimization="Release",
        module_path="/tmp/quantmodeling.so",
        module_sha256="0" * 64,
    )
    base.update(overrides)
    return BuildFingerprint(**base)


def _report(run_id: str, fingerprint: BuildFingerprint, prices: dict[str, float]) -> RunReport:
    now = datetime.now(UTC)
    return RunReport(
        run_id=run_id,
        mode="quick",
        started_at=now,
        ended_at=now,
        fingerprint=fingerprint,
        results=[
            CaseResult(
                case_id=cid, family="golden", verdict="pass", message="", observed={"price": p}
            )
            for cid, p in prices.items()
        ],
        summary={"pass": len(prices), "fail": 0, "warn": 0},
    )


def test_compare_builds_refuses_on_fingerprint_mismatch() -> None:
    baseline = _report("r1", _fingerprint(), {"a": 1.0})
    candidate = _report("r2", _fingerprint(compiler="/usr/bin/clang++"), {"a": 1.0})
    report = compare_builds(baseline, candidate)
    assert report.comparable is False
    assert report.refusal_reason is not None and "compiler" in report.refusal_reason


def test_compare_builds_allows_commit_to_differ() -> None:
    baseline = _report("r1", _fingerprint(commit="aaa"), {"a": 1.0})
    candidate = _report("r2", _fingerprint(commit="bbb"), {"a": 1.0})
    report = compare_builds(baseline, candidate)
    assert report.comparable is True


def test_compare_builds_flags_any_nonzero_drift_as_regression() -> None:
    baseline = _report("r1", _fingerprint(), {"a": 1.0, "b": 2.0})
    candidate = _report("r2", _fingerprint(), {"a": 1.0, "b": 2.0001})
    report = compare_builds(baseline, candidate)
    assert report.comparable is True
    assert report.regressions == ["b"]
    failing = [d for d in report.diffs if d.case_id == "b"][0]
    assert failing.verdict == "fail"


def test_compare_builds_no_regressions_when_identical() -> None:
    baseline = _report("r1", _fingerprint(), {"a": 1.0})
    candidate = _report("r2", _fingerprint(), {"a": 1.0})
    report = compare_builds(baseline, candidate)
    assert report.regressions == []
    assert all(d.verdict == "pass" for d in report.diffs)


def test_compare_builds_sorts_failures_first() -> None:
    baseline = _report("r1", _fingerprint(), {"a": 1.0, "b": 2.0, "c": 3.0})
    candidate = _report("r2", _fingerprint(), {"a": 1.0, "b": 2.5, "c": 3.0})
    report = compare_builds(baseline, candidate)
    assert report.diffs[0].case_id == "b"
