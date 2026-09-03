"""Drives the real `quantmodeling` pybind11 module (blueprint/10-TARGET-REPO.md §1).

No pricing logic lives here (WP09 §12): every method is a thin, generic pass-through to
the module already built by the target repo. `QuantModelingClient` is the injectable seam
(same pattern as `codeintel.client.ClangdClient`): production code uses
`RealQuantModelingClient`, tests inject a fake implementing the same contract.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from corelib.errors import DependencyError
from corelib.hashing import sha256_file

from qmharness.errors import ModuleFingerprintError
from qmharness.schemas import BuildFingerprint, CaseSpec, EngineOutcome, GreeksOutcome

CommandRunner = Callable[[list[str], Path], str]


class QuantModelingClient(Protocol):
    """Everything a check family needs from the built `quantmodeling` module."""

    def price(self, case: CaseSpec, *, timeout_s: float) -> EngineOutcome: ...

    def greeks(
        self, case: CaseSpec, which: Sequence[str], *, timeout_s: float
    ) -> GreeksOutcome: ...

    def sample_series(
        self, name: str, params: dict[str, Any], *, timeout_s: float
    ) -> list[float]: ...


class RealQuantModelingClient:
    """Wraps the real `quantmodeling` module.

    `[À CONFIRMER]` (same caveat as WP03's `registry_matrix` AST heuristic): the exact
    call signature is assumed to be `quantmodeling.price(instrument=..., model=...,
    method=..., engine=..., **inputs)` returning an object exposing `.price`,
    an optional `.std_error`, and an optional `.diagnostics` mapping — mirroring the
    visitor-pattern `PricingResult` described in 10-TARGET-REPO.md §1. Validate against
    the real module once quant-modeling is checked out before trusting this in production.
    """

    def __init__(self, module: Any) -> None:
        self._module = module

    def price(self, case: CaseSpec, *, timeout_s: float) -> EngineOutcome:
        raw = self._module.price(
            instrument=case.instrument,
            model=case.model,
            method=case.method,
            engine=case.engine,
            **case.inputs,
        )
        std_error = getattr(raw, "std_error", None)
        return EngineOutcome(
            price=float(raw.price),
            std_error=float(std_error) if std_error is not None else None,
            diagnostics=dict(getattr(raw, "diagnostics", None) or {}),
        )

    def greeks(self, case: CaseSpec, which: Sequence[str], *, timeout_s: float) -> GreeksOutcome:
        raw = self._module.greeks(
            instrument=case.instrument,
            model=case.model,
            method=case.method,
            engine=case.engine,
            which=list(which),
            **case.inputs,
        )
        return GreeksOutcome(
            values=dict(raw.values),
            std_errors=dict(getattr(raw, "std_errors", None) or {}),
        )

    def sample_series(self, name: str, params: dict[str, Any], *, timeout_s: float) -> list[float]:
        fn = getattr(self._module, name, None)
        if fn is None:
            raise DependencyError(
                f"quantmodeling has no sample series {name!r}", details={"name": name}
            )
        return [float(v) for v in fn(**params)]


def load_quantmodeling_module(build_dir: Path) -> Any:
    """Imports `quantmodeling` from the current sandbox build only, never from a wheel
    installed elsewhere (WP09 §8). Prepends `build_dir` and its documented pybind11
    output subdir (10-TARGET-REPO.md §1: `bindings/python`) to `sys.path`."""
    import importlib
    import sys

    for candidate in (build_dir, build_dir / "bindings" / "python"):
        path_str = str(candidate)
        if candidate.is_dir() and path_str not in sys.path:
            sys.path.insert(0, path_str)
    try:
        return importlib.import_module("quantmodeling")
    except ImportError as exc:
        raise DependencyError(
            "quantmodeling module not importable from the current build",
            details={"build_dir": str(build_dir)},
        ) from exc


def _default_run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise ModuleFingerprintError(
            f"command failed: {' '.join(args)}", details={"stderr": result.stderr.strip()}
        )
    return result.stdout.strip()


_CACHE_VAR_RE = re.compile(r"^(?P<key>[A-Za-z_0-9]+):[A-Za-z]+=(?P<value>.*)$")


def _read_cmake_cache(build_dir: Path) -> dict[str, str]:
    cache_path = build_dir / "CMakeCache.txt"
    if not cache_path.is_file():
        raise ModuleFingerprintError(
            "CMakeCache.txt not found; the build must be configured first",
            details={"build_dir": str(build_dir)},
        )
    values: dict[str, str] = {}
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        match = _CACHE_VAR_RE.match(line.strip())
        if match:
            values[match.group("key")] = match.group("value")
    return values


def _find_module_file(build_dir: Path) -> Path:
    matches = sorted(build_dir.rglob("quantmodeling*.so"))
    if not matches:
        raise ModuleFingerprintError(
            "no quantmodeling*.so found under the build directory",
            details={"build_dir": str(build_dir)},
        )
    return matches[0]


def build_fingerprint(
    root: Path, build_dir: Path, preset: str, *, run: CommandRunner = _default_run
) -> BuildFingerprint:
    """WP09 §8: commit + preset + compiler + version + optimization + `.so` path/hash, so
    `qmharness.compare.compare_builds()` can refuse to compare non-comparable results."""
    cache = _read_cmake_cache(build_dir)
    compiler = cache.get("CMAKE_CXX_COMPILER", "unknown")
    optimization = cache.get("CMAKE_BUILD_TYPE", "unknown")
    commit = run(["git", "rev-parse", "HEAD"], root)
    compiler_version = "unknown"
    if compiler != "unknown":
        try:
            output_lines = run([compiler, "--version"], root).splitlines()
            compiler_version = output_lines[0] if output_lines else "unknown"
        except ModuleFingerprintError:
            compiler_version = "unknown"
    module_path = _find_module_file(build_dir)
    return BuildFingerprint(
        commit=commit,
        build_preset=preset,
        compiler=compiler,
        compiler_version=compiler_version,
        optimization=optimization,
        module_path=str(module_path),
        module_sha256=sha256_file(module_path),
    )
