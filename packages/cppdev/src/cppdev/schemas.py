from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["error", "warning"]
TestStatus = Literal["passed", "failed", "skipped", "crashed"]


class RelatedLocation(BaseModel):
    """A secondary source location attached to a diagnostic (e.g. a candidate declaration)."""

    file: str
    line: int
    note: str


class Diagnostic(BaseModel):
    """One condensed compiler diagnostic. Never carries a raw multi-hundred-line trace."""

    severity: Severity
    file: str
    line: int
    column: int
    code: str | None = None
    message: str
    template_trace_omitted: int = 0
    related: list[RelatedLocation] = Field(default_factory=list)
    occurrences: int = 1


class DiagnosticsSummary(BaseModel):
    errors: int
    warnings: int
    first_error_file: str | None = None
    first_error_line: int | None = None


class DiagnosticsReport(BaseModel):
    """Errors are never truncated; warnings are, beyond `max_diagnostics`.

    Sections stay separate.
    """

    summary: DiagnosticsSummary
    errors: list[Diagnostic] = Field(default_factory=list)
    warnings: list[Diagnostic] = Field(default_factory=list)
    truncated_diagnostics: int = 0
    log_path: str | None = None


class ConfigureRequest(BaseModel):
    preset: str


class ConfigureReport(BaseModel):
    ok: bool
    preset: str
    build_dir: str
    compile_commands_path: str | None = None
    duration_ms: int
    diagnostics: DiagnosticsReport


class BuildRequest(BaseModel):
    preset: str
    target: str | None = None
    clean: bool = False
    jobs: int | None = None


class BuildReport(BaseModel):
    ok: bool
    preset: str
    target: str | None = None
    duration_ms: int
    diagnostics: DiagnosticsReport


class AssertionFailure(BaseModel):
    """A parsed gtest assertion failure, e.g. `ASSERT_NEAR(expected, actual, tolerance)`."""

    kind: str
    message: str
    expected: str | None = None
    actual: str | None = None
    tolerance: float | None = None
    delta: float | None = None


class TestCaseResult(BaseModel):
    name: str
    status: TestStatus
    duration_ms: int
    assertion: AssertionFailure | None = None


class TestRequest(BaseModel):
    __test__ = False  # not a pytest test class, just named after the `cpp.test` tool

    preset: str
    filter: str | None = None
    label: str | None = None
    jobs: int | None = None


class TestReport(BaseModel):
    __test__ = False  # not a pytest test class, just named after the `cpp.test` tool

    ok: bool
    preset: str
    total: int
    passed: int
    failed: int
    skipped: int
    crashed: int
    duration_ms: int
    cases: list[TestCaseResult] = Field(default_factory=list)


class ProjectInfo(BaseModel):
    presets: list[str]
    targets: list[str]
    build_dir: str | None = None
    configured: bool


class FormatRequest(BaseModel):
    paths: list[str]


class FormatViolation(BaseModel):
    file: str
    would_reformat: bool


class FormatReport(BaseModel):
    ok: bool
    violations: list[FormatViolation] = Field(default_factory=list)


class TidyRequest(BaseModel):
    paths: list[str]
    build_dir: str
    checks: str | None = None


class TidyReport(BaseModel):
    ok: bool
    diagnostics: DiagnosticsReport


class SanitizeRequest(BaseModel):
    preset: Literal["asan", "ubsan"]
    target: str
    args: list[str] = Field(default_factory=list)


class SanitizerFinding(BaseModel):
    kind: str
    file: str | None = None
    line: int | None = None
    message: str
    stack: list[str] = Field(default_factory=list)
    frames_omitted: int = 0


class SanitizeReport(BaseModel):
    ok: bool
    exit_code: int
    findings: list[SanitizerFinding] = Field(default_factory=list)


class CoverageRequest(BaseModel):
    preset: str
    target: str | None = None


class CoverageFile(BaseModel):
    path: str
    line_pct: float
    function_pct: float


class CoverageReport(BaseModel):
    ok: bool
    line_pct: float
    function_pct: float
    files: list[CoverageFile] = Field(default_factory=list)


class BenchRequest(BaseModel):
    preset: str
    filter: str | None = None
    reference_path: str | None = None
    threshold_pct: float = 10.0


class BenchResult(BaseModel):
    name: str
    time_ns: float
    reference_ns: float | None = None
    regression: bool = False


class BenchReport(BaseModel):
    ok: bool
    results: list[BenchResult] = Field(default_factory=list)
    llama_server_busy: bool = False
