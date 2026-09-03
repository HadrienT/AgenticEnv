from __future__ import annotations

from pathlib import Path

from cppdev.build import build, configure
from cppdev.schemas import BuildRequest, ConfigureRequest, TestRequest
from cppdev.test import run_tests


def test_run_tests_reports_a_passing_ctest_case(cmake_project: Path) -> None:
    build_dir = configure(ConfigureRequest(preset="dev"), root=cmake_project).build_dir
    build(BuildRequest(preset="dev", target="hello"), root=cmake_project)

    report = run_tests(TestRequest(preset="dev"), build_dir=Path(build_dir))

    assert report.ok is True
    assert report.total == 1
    assert report.passed == 1
    assert report.cases[0].name == "hello_runs"
    assert report.cases[0].status == "passed"


def test_run_tests_filter_selects_a_single_test_by_name(cmake_project: Path) -> None:
    build_dir = configure(ConfigureRequest(preset="dev"), root=cmake_project).build_dir
    build(BuildRequest(preset="dev", target="hello"), root=cmake_project)

    request = TestRequest(preset="dev", filter="does_not_exist")
    report = run_tests(request, build_dir=Path(build_dir))

    assert report.total == 0
