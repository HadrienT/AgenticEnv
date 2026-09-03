"""`qm` CLI: `run`, `compare`, `list-cases`, `explain-failure` (WP09 §5, §7).

`compare` deliberately takes two already-produced reports (`--baseline-report`/
`--candidate-report` JSON files, or `--baseline-run-id`/`--candidate-run-id` from
`eval.*`) rather than a git ref to check out and rebuild itself — rebuilding at an
arbitrary ref is `cpp.configure`/`cpp.build`'s job (WP02), not this package's; an
agent runs `cpp.build` at each ref, `qm run --persist` at each, then `qm compare`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from corelib.errors import AppError

from qmharness.compare import compare_builds
from qmharness.config import load_qmharness_config
from qmharness.driver import RealQuantModelingClient, build_fingerprint, load_quantmodeling_module
from qmharness.loader import discover_golden_files, load_cases
from qmharness.report import comparison_report_to_markdown, run_report_to_markdown
from qmharness.runner import run as run_harness
from qmharness.schemas import RunReport


def _cmd_run(args: argparse.Namespace) -> int:
    config = load_qmharness_config()
    root = Path(args.root)
    build_dir = root / (args.build_dir or config.build_dir)
    preset = args.preset or config.build_preset
    golden_dir = root / (args.golden_dir or config.golden_dir)

    try:
        module = load_quantmodeling_module(build_dir)
        client = RealQuantModelingClient(module)
        fingerprint = build_fingerprint(root, build_dir, preset)
        cases = load_cases(discover_golden_files(golden_dir))
        report = run_harness(cases, mode=args.mode, client=client, fingerprint=fingerprint)
    except AppError as exc:
        print(f"qm run failed: {exc.code}: {exc.message}")
        return 1

    if args.persist:
        from qmharness.store import record_run

        record_run(report)
    print(report.model_dump_json(indent=2) if args.json else run_report_to_markdown(report))
    return 0 if report.summary.get("fail", 0) == 0 else 1


def _load_report(path_arg: str | None, run_id_arg: str | None) -> RunReport:
    if path_arg is not None:
        return RunReport.model_validate_json(Path(path_arg).read_text(encoding="utf-8"))
    if run_id_arg is not None:
        from qmharness.store import get_run

        return get_run(run_id_arg)
    raise SystemExit("need either a --*-report path or a --*-run-id")


def _cmd_compare(args: argparse.Namespace) -> int:
    try:
        baseline = _load_report(args.baseline_report, args.baseline_run_id)
        candidate = _load_report(args.candidate_report, args.candidate_run_id)
        report = compare_builds(baseline, candidate)
    except AppError as exc:
        print(f"qm compare failed: {exc.code}: {exc.message}")
        return 1
    print(report.model_dump_json(indent=2) if args.json else comparison_report_to_markdown(report))
    if not report.comparable:
        return 2
    return 0 if not report.regressions else 1


def _cmd_list_cases(args: argparse.Namespace) -> int:
    config = load_qmharness_config()
    root = Path(args.root)
    golden_dir = root / (args.golden_dir or config.golden_dir)
    try:
        cases = load_cases(discover_golden_files(golden_dir))
    except AppError as exc:
        print(f"qm list-cases failed: {exc.code}: {exc.message}")
        return 1
    for case in cases:
        print(f"{case.id}\t{case.family}\t{case.instrument}\t{case.model}\t{case.method}")
    return 0


def _cmd_explain_failure(args: argparse.Namespace) -> int:
    try:
        if args.report is not None:
            report = RunReport.model_validate_json(Path(args.report).read_text(encoding="utf-8"))
            result = next((r for r in report.results if r.case_id == args.case_id), None)
            if result is None:
                print(f"no result for case {args.case_id!r} in {args.report}")
                return 1
        else:
            from qmharness.store import get_case_result

            result = get_case_result(args.run_id, args.case_id)
    except AppError as exc:
        print(f"qm explain-failure failed: {exc.code}: {exc.message}")
        return 1
    print(result.model_dump_json(indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qm")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run one family of checks in a given mode")
    p_run.add_argument("--root", default=".")
    p_run.add_argument("--build-dir")
    p_run.add_argument("--preset")
    p_run.add_argument("--golden-dir")
    p_run.add_argument("--mode", choices=["quick", "standard", "full"], default="quick")
    p_run.add_argument("--json", action="store_true")
    p_run.add_argument("--persist", action="store_true")
    p_run.set_defaults(func=_cmd_run)

    p_compare = sub.add_parser("compare", help="compare two builds over all shared cases")
    p_compare.add_argument("--baseline-report")
    p_compare.add_argument("--baseline-run-id")
    p_compare.add_argument("--candidate-report")
    p_compare.add_argument("--candidate-run-id")
    p_compare.add_argument("--json", action="store_true")
    p_compare.set_defaults(func=_cmd_compare)

    p_list = sub.add_parser("list-cases", help="list available cases by product and family")
    p_list.add_argument("--root", default=".")
    p_list.add_argument("--golden-dir")
    p_list.set_defaults(func=_cmd_list_cases)

    p_explain = sub.add_parser("explain-failure", help="detail of one failed case")
    p_explain.add_argument("--report")
    p_explain.add_argument("--run-id")
    p_explain.add_argument("--case-id", required=True)
    p_explain.set_defaults(func=_cmd_explain_failure)

    return parser


def main() -> None:
    import sys

    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
