"""Typed view of `configs/qmharness.yaml` (blueprint/06-CONFIG.md, WP09 §8). Loaded only
at the CLI/MCP boundary; `qmharness.runner`/`qmharness.compare`/`qmharness.checks.*`
never read YAML themselves (same convention as WP03/WP05's core-library-stays-config-free
decision)."""

from __future__ import annotations

from corelib.config import load_yaml_config
from pydantic import BaseModel, ConfigDict


class TolerancesConfig(BaseModel):
    golden_abs: float
    cross_engine_rel: float
    cross_engine_sigma_multiple: float
    greeks_rel: float
    zero_tolerance_abs: float


class ModesConfig(BaseModel):
    quick_max_seconds: int
    standard_max_seconds: int


class QmharnessConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    golden_dir: str
    build_dir: str
    build_preset: str
    tolerances: TolerancesConfig
    modes: ModesConfig


def load_qmharness_config() -> QmharnessConfig:
    return load_yaml_config("qmharness.yaml", QmharnessConfig)
