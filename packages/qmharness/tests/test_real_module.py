"""The harness against the real `quantmodeling` build, when this machine has one."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from qmharness.config import load_qmharness_config
from qmharness.driver import find_module_file
from qmharness.errors import ModuleFingerprintError
from qmharness.session import run_build

_ROOT = Path(os.environ.get("QM_REPO", str(Path.home() / "quant-modeling")))


def _has_build() -> bool:
    try:
        find_module_file(_ROOT / "build")
    except ModuleFingerprintError:
        return False
    return True


pytestmark = pytest.mark.skipif(not _has_build(), reason="no quantmodeling build on this machine")


def test_full_run_passes_on_the_real_module() -> None:
    report = run_build(_ROOT, config=load_qmharness_config(), mode="full", timeout_s=120)

    failures = [f"{r.case_id}: {r.message}" for r in report.results if r.verdict == "fail"]
    assert failures == []
    assert report.summary["pass"] == 9


def test_a_wrong_reference_value_is_detected(tmp_path: Path) -> None:
    (tmp_path / "wrong.yaml").write_text(
        """
- id: wrong_price
  family: golden
  instrument: EquityEuropeanOption
  model: black_scholes
  method: analytic
  engine: analytic
  inputs:
    {option_type: call, spot: 100.0, strike: 100.0, rate: 0.03, vol: 0.2, maturity_years: 1.0}
  expected: {price: 9.5}
  tolerance: {abs: 1.0e-4}
"""
    )

    report = run_build(
        _ROOT,
        config=load_qmharness_config(),
        mode="quick",
        timeout_s=60,
        golden_dir=str(tmp_path),
    )

    assert report.summary == {"pass": 0, "fail": 1, "warn": 0}
