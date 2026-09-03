"""Persists `RunReport`s to `eval.qm_runs`/`eval.qm_case_results` (WP09 §2 diagram:
`REP --> DB[(eval.*)]`). Each function opens and closes its own session, same
convention as `agentmem.episodic` — no long-lived session held across calls."""

from __future__ import annotations

from corelib.db import session_scope
from corelib.errors import NotFoundError
from corelib.serialization import to_json
from sqlalchemy import text

from qmharness.schemas import BuildFingerprint, CaseResult, RunReport


def record_run(report: RunReport) -> str:
    with session_scope() as session:
        session.execute(
            text(
                "INSERT INTO eval.qm_runs "
                "(run_id, mode, started_at, ended_at, git_commit, build_preset, compiler, "
                "compiler_version, optimization, module_path, module_sha256, summary) "
                "VALUES (:run_id, :mode, :started_at, :ended_at, :git_commit, :build_preset, "
                ":compiler, :compiler_version, :optimization, :module_path, :module_sha256, "
                "CAST(:summary AS jsonb))"
            ),
            {
                "run_id": report.run_id,
                "mode": report.mode,
                "started_at": report.started_at,
                "ended_at": report.ended_at,
                "git_commit": report.fingerprint.commit,
                "build_preset": report.fingerprint.build_preset,
                "compiler": report.fingerprint.compiler,
                "compiler_version": report.fingerprint.compiler_version,
                "optimization": report.fingerprint.optimization,
                "module_path": report.fingerprint.module_path,
                "module_sha256": report.fingerprint.module_sha256,
                "summary": to_json(report.summary),
            },
        )
        for result in report.results:
            session.execute(
                text(
                    "INSERT INTO eval.qm_case_results "
                    "(id, run_id, case_id, family, verdict, message, observed, diff_abs, "
                    "diff_rel, duration_ms) "
                    "VALUES (:id, :run_id, :case_id, :family, :verdict, :message, "
                    "CAST(:observed AS jsonb), :diff_abs, :diff_rel, :duration_ms)"
                ),
                {
                    "id": f"{report.run_id}:{result.case_id}",
                    "run_id": report.run_id,
                    "case_id": result.case_id,
                    "family": result.family,
                    "verdict": result.verdict,
                    "message": result.message,
                    "observed": to_json(result.observed),
                    "diff_abs": result.diff_abs,
                    "diff_rel": result.diff_rel,
                    "duration_ms": result.duration_ms,
                },
            )
    return report.run_id


def get_run(run_id: str) -> RunReport:
    """Rebuilds a `RunReport` from `eval.*` — used by `qm.compare`/`qm.explain_failure`
    when the caller refers to a previously persisted run by id."""
    with session_scope() as session:
        run_row = session.execute(
            text(
                "SELECT run_id, mode, started_at, ended_at, git_commit, build_preset, compiler, "
                "compiler_version, optimization, module_path, module_sha256, summary "
                "FROM eval.qm_runs WHERE run_id = :run_id"
            ),
            {"run_id": run_id},
        ).first()
        if run_row is None:
            raise NotFoundError(f"no stored run {run_id!r}", details={"run_id": run_id})
        case_rows = session.execute(
            text(
                "SELECT case_id, family, verdict, message, observed, diff_abs, diff_rel, "
                "duration_ms FROM eval.qm_case_results WHERE run_id = :run_id ORDER BY case_id"
            ),
            {"run_id": run_id},
        ).all()
    return RunReport(
        run_id=run_row.run_id,
        mode=run_row.mode,
        started_at=run_row.started_at,
        ended_at=run_row.ended_at,
        fingerprint=BuildFingerprint(
            commit=run_row.git_commit,
            build_preset=run_row.build_preset,
            compiler=run_row.compiler,
            compiler_version=run_row.compiler_version,
            optimization=run_row.optimization,
            module_path=run_row.module_path,
            module_sha256=run_row.module_sha256,
        ),
        results=[
            CaseResult(
                case_id=row.case_id,
                family=row.family,
                verdict=row.verdict,
                message=row.message,
                observed=row.observed or {},
                diff_abs=row.diff_abs,
                diff_rel=row.diff_rel,
                duration_ms=row.duration_ms,
            )
            for row in case_rows
        ],
        summary=run_row.summary or {},
    )


def get_case_result(run_id: str, case_id: str) -> CaseResult:
    """`qm.explain_failure`: fetch one stored case detail without reloading the whole
    harness (WP09 §7)."""
    with session_scope() as session:
        row = session.execute(
            text(
                "SELECT case_id, family, verdict, message, observed, diff_abs, diff_rel, "
                "duration_ms FROM eval.qm_case_results "
                "WHERE run_id = :run_id AND case_id = :case_id"
            ),
            {"run_id": run_id, "case_id": case_id},
        ).first()
    if row is None:
        raise NotFoundError(
            f"no stored result for run {run_id!r} case {case_id!r}",
            details={"run_id": run_id, "case_id": case_id},
        )
    return CaseResult(
        case_id=row.case_id,
        family=row.family,
        verdict=row.verdict,
        message=row.message,
        observed=row.observed or {},
        diff_abs=row.diff_abs,
        diff_rel=row.diff_rel,
        duration_ms=row.duration_ms,
    )
