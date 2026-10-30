"""WP15 §2: the worker process contains what the native module can do to us. A plain
`quantmodeling.py` stands in for the extension: same import, no build needed."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from qmharness.config import ApiEntry
from qmharness.driver import SubprocessQuantModelingClient
from qmharness.errors import CaseValidationError, EngineFailureError
from qmharness.runner import run
from qmharness.schemas import BuildFingerprint, CaseSpec

_MODULE = """
import os, time

class Input:
    def __init__(self):
        self.spot = 0.0
        self.maturity = 0.0
        self.is_call = False
        self.n_paths = 0

def price_ok(i):
    return {"npv": i.spot + i.n_paths if i.is_call else -1.0, "mc_std_error": 1e-315,
            "diagnostics": str(i.maturity),
            "greeks": {"delta": 0.5, "delta_std_error": 0.01, "gamma": None}}

def price_hang(i):
    time.sleep(60)

def price_crash(i):
    os.abort()

def price_raise(i):
    raise RuntimeError("bad input")
"""


@pytest.fixture
def client(tmp_path: Path) -> Iterator[SubprocessQuantModelingClient]:
    (tmp_path / "quantmodeling.py").write_text(_MODULE)
    api = [
        ApiEntry(
            instrument="I", model="m", method=name, function=f"price_{name}", input_class="Input"
        )
        for name in ("ok", "hang", "crash", "raise")
    ]
    instance = SubprocessQuantModelingClient(tmp_path / "quantmodeling.py", api)
    yield instance
    instance.close()


def _case(method: str, **inputs: object) -> CaseSpec:
    return CaseSpec(
        id=f"c_{method}",
        family="golden",
        instrument="I",
        model="m",
        method=method,
        engine="e",
        inputs={"spot": 1.0, "option_type": "call", **inputs},
        expected={"price": 1.0},
        tolerance={"abs": 1e-6},
    )


def test_price_translates_inputs_and_ignores_the_unset_std_error(
    client: SubprocessQuantModelingClient,
) -> None:
    outcome = client.price(_case("ok", maturity_years=2.0, n_paths=3.0), timeout_s=10)

    assert outcome.price == 4.0
    assert outcome.std_error is None
    assert outcome.diagnostics == {"message": "2.0"}


def test_greeks_skips_what_the_engine_does_not_give(client: SubprocessQuantModelingClient) -> None:
    outcome = client.greeks(_case("ok"), ["delta", "gamma"], timeout_s=10)

    assert outcome.values == {"delta": 0.5}
    assert outcome.std_errors == {"delta": 0.01}


def test_unknown_input_field_is_an_error_not_a_silent_default(
    client: SubprocessQuantModelingClient,
) -> None:
    with pytest.raises(EngineFailureError, match="no field 'strike'"):
        client.price(_case("ok", strike=1.0), timeout_s=10)


def test_unmapped_method_is_a_case_error(client: SubprocessQuantModelingClient) -> None:
    with pytest.raises(CaseValidationError):
        client.price(_case("nope"), timeout_s=10)


def test_hang_is_killed_at_the_timeout_and_the_next_call_works(
    client: SubprocessQuantModelingClient,
) -> None:
    with pytest.raises(EngineFailureError, match="timed out"):
        client.price(_case("hang"), timeout_s=0.5)

    assert client.price(_case("ok"), timeout_s=10).price == 1.0


def test_crash_is_reported_and_the_next_call_works(
    client: SubprocessQuantModelingClient,
) -> None:
    with pytest.raises(EngineFailureError, match="crashed"):
        client.price(_case("crash"), timeout_s=10)

    assert client.price(_case("ok"), timeout_s=10).price == 1.0


def test_a_crash_fails_its_case_and_the_run_goes_on(client: SubprocessQuantModelingClient) -> None:
    fingerprint = BuildFingerprint(
        commit="c",
        build_preset="p",
        compiler="c",
        compiler_version="v",
        optimization="o",
        module_path="m",
        module_sha256="0" * 64,
    )

    report = run(
        [_case("crash"), _case("raise"), _case("ok")],
        mode="quick",
        client=client,
        fingerprint=fingerprint,
    )

    assert [r.verdict for r in report.results] == ["fail", "fail", "pass"]
