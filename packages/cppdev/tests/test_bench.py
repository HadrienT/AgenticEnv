from __future__ import annotations

import json
from pathlib import Path

import cppdev.bench as bench_mod
import pytest
from cppdev.bench import run_bench
from cppdev.runner import CommandResult
from cppdev.schemas import BenchRequest


def test_run_bench_flags_a_regression_past_the_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = json.dumps({"benchmarks": [{"name": "price_asian", "real_time": 150.0}]})

    def fake_run_command(args: list[str], *, cwd: Path, timeout_s: int) -> CommandResult:
        return CommandResult(
            args=tuple(args), returncode=0, stdout=payload, stderr="", duration_ms=1
        )

    reference = tmp_path / "reference.json"
    reference_payload = {"benchmarks": [{"name": "price_asian", "real_time": 100.0}]}
    reference.write_text(json.dumps(reference_payload))

    monkeypatch.setattr(bench_mod, "run_command", fake_run_command)
    monkeypatch.setattr(bench_mod, "_gpu_is_busy", lambda: False)

    report = run_bench(
        BenchRequest(preset="bench", reference_path=str(reference), threshold_pct=10.0),
        binary=tmp_path / "bench_bin",
        root=tmp_path,
    )

    assert report.ok is False
    assert report.results[0].regression is True
    assert report.llama_server_busy is False
