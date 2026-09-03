from __future__ import annotations

from pathlib import Path

from cppdev.test import _parse_junit

FIXTURES = Path(__file__).parent / "fixtures"


def test_assert_near_failure_extracts_expected_actual_tolerance_and_delta() -> None:
    cases = _parse_junit(FIXTURES / "gtest_assert_near_failure.xml")

    near_case = next(c for c in cases if c.name == "PriceMatchesReferenceWithinTolerance")
    assert near_case.status == "failed"
    assert near_case.assertion is not None
    assert near_case.assertion.kind == "ASSERT_NEAR"
    assert near_case.assertion.expected == "5.5"
    assert near_case.assertion.actual == "4"
    assert near_case.assertion.tolerance == 0.1
    assert near_case.assertion.delta == 1.5


def test_segfault_is_distinguished_from_a_regular_assertion_failure() -> None:
    cases = _parse_junit(FIXTURES / "gtest_assert_near_failure.xml")

    crashed_case = next(c for c in cases if c.name == "SegfaultsOnMalformedSchedule")
    assert crashed_case.status == "crashed"
