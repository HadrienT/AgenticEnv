"""Drives the real `quantmodeling` pybind11 module (blueprint/10-TARGET-REPO.md §1).

No pricing logic lives here (WP09 §12): every method is a thin, generic pass-through to
the module already built by the target repo. `QuantModelingClient` is the injectable seam
(same pattern as `codeintel.client.ClangdClient`): production code uses
`SubprocessQuantModelingClient`, tests inject a fake implementing the same contract.
"""

from __future__ import annotations

import json
import re
import select
import subprocess
import sys
from collections.abc import Callable, Sequence
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path
from typing import Any, Protocol

from corelib.hashing import sha256_file

from qmharness.config import ApiEntry
from qmharness.errors import CaseValidationError, EngineFailureError, ModuleFingerprintError
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


# Under this, `mc_std_error` is not an error estimate: the module leaves the field
# unset for deterministic engines, and it reads as a denormal.
_MIN_STD_ERROR = 1.0e-200
_KEEP_STDERR_CHARS = 2000


class SubprocessQuantModelingClient:
    """Calls the real `quantmodeling` module through `qmharness.worker`, one process per
    run. `timeout_s` really bounds each call: the worker is killed and restarted past
    it. A crash or a timeout raises `EngineFailureError`, which fails that case only.
    """

    def __init__(self, module_path: Path, api: Sequence[ApiEntry]) -> None:
        self._module_path = module_path
        self._api = {(e.instrument, e.model, e.method): e for e in api}
        self._process: subprocess.Popen[str] | None = None

    def close(self) -> None:
        if self._process is not None:
            self._process.kill()
            self._process.wait()
            self._process = None

    def _worker(self) -> subprocess.Popen[str]:
        if self._process is None or self._process.poll() is not None:
            self._process = subprocess.Popen(
                [sys.executable, "-m", "qmharness.worker", str(self._module_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        return self._process

    def _call(self, request: dict[str, Any], *, timeout_s: float) -> Any:
        process = self._worker()
        assert process.stdin is not None and process.stdout is not None
        try:
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
        except BrokenPipeError:
            pass  # the crash is reported below, with its stderr
        ready, _, _ = select.select([process.stdout], [], [], timeout_s)
        if not ready:
            self.close()
            raise EngineFailureError(
                f"quantmodeling call timed out after {timeout_s:.0f}s",
                details={"function": request["function"]},
            )
        line = process.stdout.readline()
        if not line:
            process.wait()
            stderr = process.stderr.read() if process.stderr else ""
            self._process = None
            raise EngineFailureError(
                f"quantmodeling crashed (exit code {process.returncode})",
                details={"function": request["function"], "stderr": stderr[-_KEEP_STDERR_CHARS:]},
            )
        response = json.loads(line)
        if not response["ok"]:
            raise EngineFailureError(
                f"quantmodeling refused the call: {response['error']}",
                details={"function": request["function"]},
            )
        return response["result"]

    def _price_raw(self, case: CaseSpec, *, timeout_s: float) -> dict[str, Any]:
        entry = self._api.get((case.instrument, case.model, case.method))
        if entry is None:
            raise CaseValidationError(
                f"no quantmodeling function for {case.instrument}/{case.model}/{case.method}",
                details={"case_id": case.id},
            )
        request = {
            "kind": "price",
            "function": entry.function,
            "input_class": entry.input_class,
            "inputs": case.inputs,
        }
        result: dict[str, Any] = self._call(request, timeout_s=timeout_s)
        return result

    def price(self, case: CaseSpec, *, timeout_s: float) -> EngineOutcome:
        raw = self._price_raw(case, timeout_s=timeout_s)
        std_error = raw.get("mc_std_error")
        return EngineOutcome(
            price=float(raw["npv"]),
            std_error=float(std_error) if std_error and std_error > _MIN_STD_ERROR else None,
            diagnostics={"message": raw.get("diagnostics", "")},
        )

    def greeks(self, case: CaseSpec, which: Sequence[str], *, timeout_s: float) -> GreeksOutcome:
        greeks = self._price_raw(case, timeout_s=timeout_s)["greeks"]
        values = {name: float(greeks[name]) for name in which if greeks.get(name) is not None}
        errors = {
            name: float(greeks[f"{name}_std_error"])
            for name in which
            if greeks.get(f"{name}_std_error") is not None
        }
        return GreeksOutcome(values=values, std_errors=errors)

    def sample_series(self, name: str, params: dict[str, Any], *, timeout_s: float) -> list[float]:
        request = {"kind": "series", "function": name, "params": params}
        return [float(v) for v in self._call(request, timeout_s=timeout_s)]


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


def find_module_file(build_dir: Path) -> Path:
    """The extension this interpreter can load: a build tree may hold one per Python."""
    matches = sorted(build_dir.rglob(f"quantmodeling{EXTENSION_SUFFIXES[0]}"))
    if not matches:
        raise ModuleFingerprintError(
            f"no quantmodeling{EXTENSION_SUFFIXES[0]} found under the build directory",
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
    module_path = find_module_file(build_dir)
    return BuildFingerprint(
        commit=commit,
        build_preset=preset,
        compiler=compiler,
        compiler_version=compiler_version,
        optimization=optimization,
        module_path=str(module_path),
        module_sha256=sha256_file(module_path),
    )
