from __future__ import annotations

from pathlib import Path

import pytest
from qmharness.errors import CaseValidationError
from qmharness.loader import discover_golden_files, load_cases, load_cases_from_file


def test_load_cases_from_file_parses_valid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "cases.yaml"
    path.write_text(
        """
- id: bs_call_atm_1y
  family: golden
  instrument: EquityEuropeanOption
  model: black_scholes
  method: analytic
  engine: analytic
  inputs: {spot: 100.0, strike: 100.0, rate: 0.03, vol: 0.20, maturity_years: 1.0}
  expected: {price: 10.4506}
  tolerance: {abs: 1.0e-4}
  source: "Hull 11th ed., closed-form Black-Scholes-Merton"
""",
        encoding="utf-8",
    )
    cases = load_cases_from_file(path)
    assert len(cases) == 1
    assert cases[0].id == "bs_call_atm_1y"
    assert cases[0].expected == {"price": 10.4506}


def test_load_cases_from_file_rejects_non_list(tmp_path: Path) -> None:
    path = tmp_path / "cases.yaml"
    path.write_text("id: not_a_list\n", encoding="utf-8")
    with pytest.raises(CaseValidationError):
        load_cases_from_file(path)


def test_load_cases_from_file_rejects_malformed_case(tmp_path: Path) -> None:
    path = tmp_path / "cases.yaml"
    path.write_text("- id: missing_required_fields\n", encoding="utf-8")
    with pytest.raises(CaseValidationError):
        load_cases_from_file(path)


def test_load_cases_from_file_rejects_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "cases.yaml"
    path.write_text("- id: [unterminated\n", encoding="utf-8")
    with pytest.raises(CaseValidationError):
        load_cases_from_file(path)


def test_discover_golden_files_globs_yaml(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("- {}\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("- {}\n", encoding="utf-8")
    (tmp_path / "readme.md").write_text("not a case file\n", encoding="utf-8")
    found = discover_golden_files(tmp_path)
    assert [p.name for p in found] == ["a.yaml", "b.yaml"]


def test_load_cases_concatenates_all_files(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(
        "- {id: a, family: golden, instrument: X, model: m, method: me, engine: e}\n",
        encoding="utf-8",
    )
    (tmp_path / "b.yaml").write_text(
        "- {id: b, family: golden, instrument: X, model: m, method: me, engine: e}\n",
        encoding="utf-8",
    )
    cases = load_cases(discover_golden_files(tmp_path))
    assert [c.id for c in cases] == ["a", "b"]
