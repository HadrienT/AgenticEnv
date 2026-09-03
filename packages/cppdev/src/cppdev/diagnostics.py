from __future__ import annotations

import re
from pathlib import Path

from cppdev.schemas import (
    Diagnostic,
    DiagnosticsReport,
    DiagnosticsSummary,
    RelatedLocation,
    Severity,
)

# gcc and clang share this line shape: "<file>:<line>:<col>: <severity>: <message>"
_DIAG_RE = re.compile(
    r"^(?P<file>[^\s:][^:]*):(?P<line>\d+):(?P<column>\d+): "
    r"(?P<severity>error|warning|note): (?P<message>.*)$"
)

# Lines that are part of a template-instantiation trace, in either gcc or clang phrasing.
# These are folded: counted, never shown, never turned into a `related` entry.
_TRACE_RE = re.compile(
    r"(in instantiation of|instantiated from|required from|requested here"
    r"|in substitution of|required by substitution)",
    re.IGNORECASE,
)

_MAX_MESSAGE_LEN = 300


def _relativize(file: str, workspace_root: Path) -> str:
    path = Path(file)
    if not path.is_absolute():
        return file
    try:
        return str(path.relative_to(workspace_root))
    except ValueError:
        return file  # e.g. a system header: not under the workspace, not a host leak


def _condense(message: str) -> str:
    message = message.strip()
    if len(message) > _MAX_MESSAGE_LEN:
        return message[: _MAX_MESSAGE_LEN - 1] + "…"
    return message


def parse_compiler_output(
    raw: str,
    *,
    workspace_root: Path,
    max_warnings: int = 20,
) -> DiagnosticsReport:
    """Parses concatenated gcc/clang stdout+stderr into condensed, deduplicated diagnostics.

    Template-instantiation chains are folded to a counter; notes that don't reference an
    instantiation trace (e.g. "candidate declared here") become `related` locations instead.
    """
    errors: dict[tuple[str, int, int, str], Diagnostic] = {}
    warnings: dict[tuple[str, int, int, str], Diagnostic] = {}
    order: list[tuple[Severity, tuple[str, int, int, str]]] = []

    pending_trace_count = 0
    last_key: tuple[Severity, tuple[str, int, int, str]] | None = None

    for line in raw.splitlines():
        match = _DIAG_RE.match(line)
        if match is None:
            if _TRACE_RE.search(line):
                if last_key is not None:
                    bucket = errors if last_key[0] == "error" else warnings
                    bucket[last_key[1]].template_trace_omitted += 1
                else:
                    pending_trace_count += 1
            continue  # source snippet / caret / "In file included from" noise: dropped

        file = _relativize(match.group("file"), workspace_root)
        line_no = int(match.group("line"))
        column = int(match.group("column"))
        severity = match.group("severity")
        message = _condense(match.group("message"))

        if severity == "note":
            if _TRACE_RE.search(message):
                if last_key is not None:
                    bucket = errors if last_key[0] == "error" else warnings
                    bucket[last_key[1]].template_trace_omitted += 1
                else:
                    pending_trace_count += 1
            elif last_key is not None:
                bucket = errors if last_key[0] == "error" else warnings
                bucket[last_key[1]].related.append(
                    RelatedLocation(file=file, line=line_no, note=message)
                )
            continue

        key = (file, line_no, column, message)
        bucket = errors if severity == "error" else warnings
        if key in bucket:
            bucket[key].occurrences += 1
        else:
            diagnostic = Diagnostic(
                severity=severity,
                file=file,
                line=line_no,
                column=column,
                message=message,
                template_trace_omitted=pending_trace_count,
            )
            bucket[key] = diagnostic
            order.append((severity, key))  # type: ignore[arg-type]
        pending_trace_count = 0
        last_key = (severity, key)  # type: ignore[assignment]

    ordered_errors = [errors[key] for sev, key in order if sev == "error"]
    ordered_warnings = [warnings[key] for sev, key in order if sev == "warning"]

    truncated = max(0, len(ordered_warnings) - max_warnings)
    kept_warnings = ordered_warnings[:max_warnings]

    summary = DiagnosticsSummary(
        errors=len(ordered_errors),
        warnings=len(ordered_warnings),
        first_error_file=ordered_errors[0].file if ordered_errors else None,
        first_error_line=ordered_errors[0].line if ordered_errors else None,
    )
    return DiagnosticsReport(
        summary=summary,
        errors=ordered_errors,
        warnings=kept_warnings,
        truncated_diagnostics=truncated,
    )
