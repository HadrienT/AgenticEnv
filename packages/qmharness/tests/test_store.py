from __future__ import annotations

from datetime import UTC, datetime

import pytest
from corelib.errors import NotFoundError
from qmharness.schemas import BuildFingerprint, CaseResult, RunReport
from qmharness.store import get_case_result, get_run, record_run

pytestmark = pytest.mark.integration


def _report(run_id: str) -> RunReport:
    now = datetime.now(UTC)
    fingerprint = BuildFingerprint(
        commit="abc1234",
        build_preset="release",
        compiler="/usr/bin/c++",
        compiler_version="13.2.0",
        optimization="Release",
        module_path="/tmp/quantmodeling.so",
        module_sha256="0" * 64,
    )
    return RunReport(
        run_id=run_id,
        mode="quick",
        started_at=now,
        ended_at=now,
        fingerprint=fingerprint,
        results=[
            CaseResult(
                case_id="bs_call_atm_1y",
                family="golden",
                verdict="pass",
                message="ok",
                observed={"price": 9.4134},
                diff_abs=0.0,
            ),
        ],
        summary={"pass": 1, "fail": 0, "warn": 0},
    )


def test_record_run_then_get_run_roundtrips(clean_eval_tables: None) -> None:
    report = _report("run-store-1")
    run_id = record_run(report)
    assert run_id == "run-store-1"
    fetched = get_run(run_id)
    assert fetched.run_id == report.run_id
    assert fetched.fingerprint.commit == "abc1234"
    assert fetched.summary == {"pass": 1, "fail": 0, "warn": 0}
    assert len(fetched.results) == 1
    assert fetched.results[0].case_id == "bs_call_atm_1y"


def test_get_run_unknown_raises_not_found(clean_eval_tables: None) -> None:
    with pytest.raises(NotFoundError):
        get_run("does-not-exist")


def test_get_case_result_returns_stored_detail(clean_eval_tables: None) -> None:
    report = _report("run-store-2")
    record_run(report)
    result = get_case_result("run-store-2", "bs_call_atm_1y")
    assert result.verdict == "pass"
    assert result.observed == {"price": 9.4134}


def test_get_case_result_unknown_raises_not_found(clean_eval_tables: None) -> None:
    report = _report("run-store-3")
    record_run(report)
    with pytest.raises(NotFoundError):
        get_case_result("run-store-3", "no-such-case")
