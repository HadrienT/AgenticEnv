from __future__ import annotations

from qmharness.runner import run
from qmharness.schemas import BuildFingerprint, CaseSpec, EngineOutcome


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


def test_run_filters_cases_by_mode(fake_client) -> None:
    fake_client.price_fn = lambda c: EngineOutcome(price=9.4134)
    cases = [
        CaseSpec(
            id="golden_1",
            family="golden",
            instrument="X",
            model="m",
            method="me",
            engine="e",
            expected={"price": 9.4134},
            tolerance={"abs": 1e-6},
        ),
        CaseSpec(
            id="greeks_1",
            family="greeks",
            instrument="X",
            model="m",
            method="me",
            engine="e",
            family_params={"methods": ["a", "b"]},
        ),
    ]
    report = run(cases, mode="quick", client=fake_client, fingerprint=_fingerprint())
    assert [r.case_id for r in report.results] == ["golden_1"]
    assert report.summary["pass"] == 1
    assert report.summary["fail"] == 0


def test_run_aggregates_pass_fail_counts(fake_client) -> None:
    fake_client.price_fn = lambda c: EngineOutcome(price=0.0)
    cases = [
        CaseSpec(
            id="ok",
            family="golden",
            instrument="X",
            model="m",
            method="me",
            engine="e",
            expected={"price": 0.0},
            tolerance={"abs": 1e-6},
        ),
        CaseSpec(
            id="bad",
            family="golden",
            instrument="X",
            model="m",
            method="me",
            engine="e",
            expected={"price": 100.0},
            tolerance={"abs": 1e-6},
        ),
    ]
    report = run(cases, mode="quick", client=fake_client, fingerprint=_fingerprint())
    assert report.summary == {"pass": 1, "fail": 1, "warn": 0}


def test_run_sets_duration_and_fingerprint(fake_client) -> None:
    fake_client.price_fn = lambda c: EngineOutcome(price=1.0)
    cases = [
        CaseSpec(
            id="ok",
            family="golden",
            instrument="X",
            model="m",
            method="me",
            engine="e",
            expected={"price": 1.0},
            tolerance={"abs": 1e-6},
        ),
    ]
    fingerprint = _fingerprint()
    report = run(cases, mode="quick", client=fake_client, fingerprint=fingerprint)
    assert report.fingerprint == fingerprint
    assert report.results[0].duration_ms >= 0
