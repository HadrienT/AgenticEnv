"""Domain schemas for qmharness (blueprint/wp/WP09-numerical-harness.md §3, §6).

`CaseSpec.family_params` is a deliberately flexible bag: each check family (golden,
cross_engine, invariants, convergence, statistics, greeks) needs different auxiliary
parameters (which invariant, which methods to cross-check, which N values to sweep...),
and exploding `CaseSpec` with one optional field per family would make it unreadable.
Each `qmharness.checks.<family>` module documents the keys it reads from this dict.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

CheckFamily = Literal["golden", "cross_engine", "invariants", "convergence", "statistics", "greeks"]
RunMode = Literal["quick", "standard", "full"]
Verdict = Literal["pass", "fail", "warn"]

# WP09 §4: quick must stay cheap enough that an agent runs it without hesitating.
FAMILIES_BY_MODE: dict[RunMode, tuple[CheckFamily, ...]] = {
    "quick": ("golden", "invariants"),
    "standard": ("golden", "invariants", "cross_engine", "greeks"),
    "full": ("golden", "invariants", "cross_engine", "greeks", "convergence", "statistics"),
}


class CaseSpec(BaseModel):
    """One versioned test case, loaded from `benchmarks/golden/*.yaml` (WP09 §3, §6)."""

    id: str
    family: CheckFamily
    instrument: str
    model: str
    method: str
    engine: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, float] | None = None
    tolerance: dict[str, float] = Field(default_factory=dict)
    source: str | None = None
    tags: list[str] = Field(default_factory=list)
    family_params: dict[str, Any] = Field(default_factory=dict)


class EngineOutcome(BaseModel):
    """One `price()` call's result. `extra` carries engine-specific numeric diagnostics
    (e.g. `n_paths`, `ci_half_width`) without hardcoding every possible field."""

    price: float
    std_error: float | None = None
    extra: dict[str, float] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class GreeksOutcome(BaseModel):
    values: dict[str, float]
    std_errors: dict[str, float] = Field(default_factory=dict)


class BuildFingerprint(BaseModel):
    """WP09 §8: two runs are only comparable if these fields agree exactly."""

    commit: str
    build_preset: str
    compiler: str
    compiler_version: str
    optimization: str
    module_path: str
    module_sha256: str


class CaseResult(BaseModel):
    case_id: str
    family: CheckFamily
    verdict: Verdict
    message: str
    observed: dict[str, float] = Field(default_factory=dict)
    expected: dict[str, float] | None = None
    diff_abs: float | None = None
    diff_rel: float | None = None
    duration_ms: int = 0


class RunReport(BaseModel):
    run_id: str
    mode: RunMode
    started_at: datetime
    ended_at: datetime
    fingerprint: BuildFingerprint
    results: list[CaseResult] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


class ComparisonCaseDiff(BaseModel):
    case_id: str
    baseline_price: float
    candidate_price: float
    diff_abs: float
    diff_rel: float
    verdict: Verdict
    note: str = ""


class ComparisonReport(BaseModel):
    comparable: bool
    refusal_reason: str | None = None
    baseline_fingerprint: BuildFingerprint | None = None
    candidate_fingerprint: BuildFingerprint | None = None
    diffs: list[ComparisonCaseDiff] = Field(default_factory=list)
    regressions: list[str] = Field(default_factory=list)
