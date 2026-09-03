from __future__ import annotations

import shutil
from pathlib import Path

from cppdev.diagnostics import parse_compiler_output
from cppdev.errors import ToolMissingError
from cppdev.project import resolve_build_dir
from cppdev.runner import run_command
from cppdev.schemas import BuildReport, BuildRequest, ConfigureReport, ConfigureRequest

_DEFAULT_CONFIGURE_TIMEOUT_S = 300
_DEFAULT_BUILD_TIMEOUT_S = 900


def configure(
    request: ConfigureRequest, *, root: Path, timeout_s: int = _DEFAULT_CONFIGURE_TIMEOUT_S
) -> ConfigureReport:
    """`cmake --preset <p>`. Regenerates `compile_commands.json`, the source of truth for WP03."""
    if shutil.which("cmake") is None:
        raise ToolMissingError("cmake not found on PATH", details={"tool": "cmake"})
    result = run_command(["cmake", "--preset", request.preset], cwd=root, timeout_s=timeout_s)
    combined = result.stdout + result.stderr
    diagnostics = parse_compiler_output(combined, workspace_root=root)
    build_dir = resolve_build_dir(root, request.preset)
    compile_commands = build_dir / "compile_commands.json"
    return ConfigureReport(
        ok=result.returncode == 0,
        preset=request.preset,
        build_dir=str(build_dir),
        compile_commands_path=str(compile_commands) if compile_commands.is_file() else None,
        duration_ms=result.duration_ms,
        diagnostics=diagnostics,
    )


def build(
    request: BuildRequest,
    *,
    root: Path,
    timeout_s: int = _DEFAULT_BUILD_TIMEOUT_S,
    max_jobs: int | None = None,
) -> BuildReport:
    """Incremental build of one target by default (B3/B6); `clean` is opt-in, never implicit."""
    if shutil.which("cmake") is None:
        raise ToolMissingError("cmake not found on PATH", details={"tool": "cmake"})
    build_dir = resolve_build_dir(root, request.preset)

    if request.clean:
        clean_args = ["cmake", "--build", str(build_dir), "--target", "clean"]
        run_command(clean_args, cwd=root, timeout_s=timeout_s)

    args = ["cmake", "--build", str(build_dir)]
    if request.target is not None:
        args += ["--target", request.target]
    jobs = request.jobs if request.jobs is not None else max_jobs
    if jobs is not None:
        args += ["--parallel", str(jobs)]

    result = run_command(args, cwd=root, timeout_s=timeout_s)
    combined = result.stdout + result.stderr
    diagnostics = parse_compiler_output(combined, workspace_root=root)
    return BuildReport(
        ok=result.returncode == 0,
        preset=request.preset,
        target=request.target,
        duration_ms=result.duration_ms,
        diagnostics=diagnostics,
    )
