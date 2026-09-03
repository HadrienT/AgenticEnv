from __future__ import annotations

import re
from pathlib import Path

from cppdev.runner import run_command
from cppdev.schemas import SanitizeReport, SanitizeRequest, SanitizerFinding

_DEFAULT_TIMEOUT_S = 1800

_ASAN_HEADER_RE = re.compile(r"==\d+==ERROR: (?P<kind>\w+Sanitizer): (?P<message>.*)")
_UBSAN_HEADER_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):\d+: runtime error: (?P<message>.*)$"
)
_FRAME_RE = re.compile(r"^\s*#\d+ .* in .* (?P<file>[^\s:]+):(?P<line>\d+):\d+$")
_MAX_STACK_FRAMES = 10


def _relativize(file: str, workspace_root: Path) -> str | None:
    path = Path(file)
    if not path.is_absolute():
        return file
    try:
        return str(path.relative_to(workspace_root))
    except ValueError:
        return None  # frame outside the project: folded, not shown


def _parse_findings(raw: str, *, workspace_root: Path) -> list[SanitizerFinding]:
    findings: list[SanitizerFinding] = []
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        asan_match = _ASAN_HEADER_RE.search(lines[i])
        ubsan_match = _UBSAN_HEADER_RE.match(lines[i])
        if asan_match is None and ubsan_match is None:
            i += 1
            continue

        if asan_match is not None:
            kind = asan_match.group("kind")
            message = asan_match.group("message")
            file: str | None = None
            line_no: int | None = None
        else:
            assert ubsan_match is not None
            kind = "UndefinedBehaviorSanitizer"
            message = ubsan_match.group("message")
            file = _relativize(ubsan_match.group("file"), workspace_root)
            line_no = int(ubsan_match.group("line"))

        stack: list[str] = []
        frames_omitted = 0
        i += 1
        # ASan/UBSan interleave explanatory lines (e.g. "READ of size N at ADDR
        # thread TN") between the header and the actual stack frames; skip them.
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("#"):
            i += 1
        while i < len(lines) and lines[i].strip().startswith("#"):
            frame_match = _FRAME_RE.match(lines[i])
            if frame_match is not None:
                project_file = _relativize(frame_match.group("file"), workspace_root)
                if project_file is not None:
                    if len(stack) < _MAX_STACK_FRAMES:
                        stack.append(f"{project_file}:{frame_match.group('line')}")
                    else:
                        frames_omitted += 1
                else:
                    frames_omitted += 1
            else:
                frames_omitted += 1  # e.g. a libc frame with no file:line info
            i += 1
        findings.append(
            SanitizerFinding(
                kind=kind,
                file=file,
                line=line_no,
                message=message,
                stack=stack,
                frames_omitted=frames_omitted,
            )
        )
    return findings


def run_sanitize(
    request: SanitizeRequest,
    *,
    build_dir: Path,
    root: Path,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> SanitizeReport:
    """Runs the already-built (asan/ubsan preset) executable; folds frames outside the project."""
    binary = build_dir / request.target
    result = run_command([str(binary), *request.args], cwd=root, timeout_s=timeout_s)
    findings = _parse_findings(result.stdout + result.stderr, workspace_root=root)
    return SanitizeReport(
        ok=result.returncode == 0 and not findings,
        exit_code=result.returncode,
        findings=findings,
    )
