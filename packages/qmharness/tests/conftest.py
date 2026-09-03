from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import pytest
from corelib.db import apply_migrations, session_scope
from qmharness.schemas import CaseSpec, EngineOutcome, GreeksOutcome
from sqlalchemy import text


@pytest.fixture
def clean_eval_tables() -> None:
    """Truncates `eval.*` so integration tests get a clean slate (same convention as
    agentmem's `clean_mem_tables`)."""
    apply_migrations()
    with session_scope() as session:
        session.execute(text("TRUNCATE eval.qm_case_results, eval.qm_runs"))


class FakeQuantModelingClient:
    """In-memory double for `QuantModelingClient`. Tests set the `price_fn`/`greeks_fn`/
    `series_fn` callables directly on the fixture instance (same convention as
    codeintel's `FakeClangdClient`), so each test controls exactly what the "C++
    library" would have returned, without needing the real `quantmodeling` module."""

    def __init__(self) -> None:
        self.price_calls: list[CaseSpec] = []
        self.greeks_calls: list[tuple[CaseSpec, tuple[str, ...]]] = []
        self.price_fn: Callable[[CaseSpec], EngineOutcome] = lambda case: EngineOutcome(price=0.0)
        self.greeks_fn: Callable[[CaseSpec, Sequence[str]], GreeksOutcome] = lambda case, which: (
            GreeksOutcome(values=dict.fromkeys(which, 0.0))
        )
        self.series_fn: Callable[[str, dict[str, Any]], list[float]] = lambda name, params: []

    def price(self, case: CaseSpec, *, timeout_s: float) -> EngineOutcome:
        self.price_calls.append(case)
        return self.price_fn(case)

    def greeks(self, case: CaseSpec, which: Sequence[str], *, timeout_s: float) -> GreeksOutcome:
        self.greeks_calls.append((case, tuple(which)))
        return self.greeks_fn(case, which)

    def sample_series(self, name: str, params: dict[str, Any], *, timeout_s: float) -> list[float]:
        return self.series_fn(name, params)


@pytest.fixture
def fake_client() -> FakeQuantModelingClient:
    return FakeQuantModelingClient()


@pytest.fixture
def base_case() -> CaseSpec:
    return CaseSpec(
        id="bs_call_atm_1y",
        family="golden",
        instrument="EquityEuropeanOption",
        model="black_scholes",
        method="analytic",
        engine="analytic",
        inputs={
            "option_type": "call",
            "spot": 100.0,
            "strike": 100.0,
            "rate": 0.03,
            "dividend": 0.0,
            "vol": 0.20,
            "maturity_years": 1.0,
        },
    )
