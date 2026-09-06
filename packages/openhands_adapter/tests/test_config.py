from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from openhands_adapter.config import OpenHandsConfig
from pydantic import ValidationError

_REPO_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "openhands.yaml"


def test_committed_openhands_yaml_validates_against_the_model() -> None:
    """Catches drift between configs/openhands.yaml and OpenHandsConfig without
    going through corelib's Settings wiring (no package tests that, cf.
    packages/corelib/tests/test_config.py; every domain package's own config
    model is validated directly, same convention)."""
    raw = yaml.safe_load(_REPO_CONFIG.read_text())

    cfg = OpenHandsConfig.model_validate(raw)

    assert cfg.sandbox.image
    assert cfg.sandbox.platform == "linux/amd64"
    assert cfg.llm.sandbox_base_url.startswith("http://")
    assert cfg.run.max_iterations > 0
    assert cfg.run.timeout_s > 0


def test_missing_required_field_raises_validation_error() -> None:
    raw = yaml.safe_load(_REPO_CONFIG.read_text())
    del raw["llm"]["sandbox_base_url"]

    with pytest.raises(ValidationError):
        OpenHandsConfig.model_validate(raw)


def test_unknown_top_level_key_is_ignored_not_rejected() -> None:
    raw = yaml.safe_load(_REPO_CONFIG.read_text())
    raw["sandbox"]["unknown_future_field"] = "whatever"

    cfg = OpenHandsConfig.model_validate(raw)

    assert cfg.sandbox.image
