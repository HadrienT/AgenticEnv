from __future__ import annotations

from corelib.errors import AppError, ConfigError, ValidationError


def test_app_error_to_dto_carries_code_message_details_retryable() -> None:
    err = ValidationError("bad rate", details={"field": "rate", "value": 3.0})
    dto = err.to_dto()
    assert dto.code == "VALIDATION_ERROR"
    assert dto.message == "bad rate"
    assert dto.details == {"field": "rate", "value": 3.0}
    assert dto.retryable is False


def test_config_error_is_not_retryable() -> None:
    assert ConfigError("missing var").retryable is False


def test_app_error_details_default_to_empty_mapping() -> None:
    assert AppError("boom").details == {}
