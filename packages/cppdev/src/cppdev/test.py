from __future__ import annotations

import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import NamedTemporaryFile

from cppdev.errors import ToolMissingError
from cppdev.runner import run_command
from cppdev.schemas import AssertionFailure, TestCaseResult, TestReport, TestRequest, TestStatus

_DEFAULT_TIMEOUT_S = 900

# googletest's ASSERT_NEAR/EXPECT_NEAR failure message shape (current googletest versions).
_FLOAT = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
_NEAR_RE = re.compile(
    rf"difference between .*? is (?P<delta>{_FLOAT}), which exceeds .*?, where"
    rf".*?evaluates to (?P<val1>{_FLOAT}),"
    rf".*?evaluates to (?P<val2>{_FLOAT}),"
    rf".*?evaluates to (?P<tol>{_FLOAT})\.?",
    re.DOTALL,
)

# googletest's ASSERT_EQ/EXPECT_EQ failure message shape.
_EQ_RE = re.compile(
    r"Expected equality of these values:\s*\n\s*.+\n\s*Which is: (?P<expected>.+)\n"
    r"\s*.+\n\s*Which is: (?P<actual>.+)"
)


def _parse_assertion(message: str) -> AssertionFailure:
    near = _NEAR_RE.search(message)
    if near is not None:
        return AssertionFailure(
            kind="ASSERT_NEAR",
            message=message.strip().splitlines()[0],
            expected=near.group("val1"),
            actual=near.group("val2"),
            tolerance=float(near.group("tol")),
            delta=float(near.group("delta")),
        )
    eq = _EQ_RE.search(message)
    if eq is not None:
        return AssertionFailure(
            kind="ASSERT_EQ",
            message=message.strip().splitlines()[0],
            expected=eq.group("expected").strip(),
            actual=eq.group("actual").strip(),
        )
    first_line = next((line for line in message.strip().splitlines() if line.strip()), message)
    return AssertionFailure(kind="unknown", message=first_line.strip())


def _parse_junit(report_path: Path) -> list[TestCaseResult]:
    root = ET.parse(report_path).getroot()  # noqa: S314 - our own ctest output, not untrusted input
    cases: list[TestCaseResult] = []
    for testcase in root.iter("testcase"):
        name = testcase.get("name", "?")
        duration_ms = int(float(testcase.get("time", "0")) * 1000)
        failure = testcase.find("failure")
        error = testcase.find("error")
        skipped = testcase.find("skipped")
        status: TestStatus
        assertion: AssertionFailure | None = None
        if error is not None:
            status = "crashed"  # ctest maps aborted/exception subprocesses to <error>
            assertion = _parse_assertion(error.get("message") or error.text or "")
        elif failure is not None:
            status = "failed"
            assertion = _parse_assertion(failure.get("message") or failure.text or "")
        elif skipped is not None:
            status = "skipped"
        else:
            status = "passed"
        cases.append(
            TestCaseResult(name=name, status=status, duration_ms=duration_ms, assertion=assertion)
        )
    return cases


def run_tests(
    request: TestRequest, *, build_dir: Path, timeout_s: int = _DEFAULT_TIMEOUT_S
) -> TestReport:
    """`ctest`, filtered by name/label (T1), never mutates source (T4)."""
    if shutil.which("ctest") is None:
        raise ToolMissingError("ctest not found on PATH", details={"tool": "ctest"})

    with NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        junit_path = Path(tmp.name)
    try:
        args = ["ctest", "--test-dir", str(build_dir), "--output-junit", str(junit_path)]
        if request.filter is not None:
            args += ["-R", request.filter]
        if request.label is not None:
            args += ["-L", request.label]
        if request.jobs is not None:
            args += ["-j", str(request.jobs)]
        result = run_command(args, cwd=build_dir, timeout_s=timeout_s)
        cases = _parse_junit(junit_path) if junit_path.is_file() else []
    finally:
        junit_path.unlink(missing_ok=True)

    passed = sum(1 for c in cases if c.status == "passed")
    failed = sum(1 for c in cases if c.status == "failed")
    skipped = sum(1 for c in cases if c.status == "skipped")
    crashed = sum(1 for c in cases if c.status == "crashed")
    return TestReport(
        ok=result.returncode == 0,
        preset=request.preset,
        total=len(cases),
        passed=passed,
        failed=failed,
        skipped=skipped,
        crashed=crashed,
        duration_ms=result.duration_ms,
        cases=cases,
    )
