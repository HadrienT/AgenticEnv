from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from pydantic import BaseModel


class ErrorDTO(BaseModel):
    """Wire representation of an `AppError`, sent across the MCP boundary."""

    code: str
    message: str
    details: Mapping[str, Any]
    retryable: bool


class AppError(Exception):
    """Root of the application error taxonomy. Never caught and discarded."""

    code: ClassVar[str] = "INTERNAL_ERROR"
    retryable: ClassVar[bool] = False

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: Mapping[str, Any] = details or {}

    def to_dto(self) -> ErrorDTO:
        return ErrorDTO(
            code=self.code,
            message=self.message,
            details=self.details,
            retryable=self.retryable,
        )


class ConfigError(AppError):
    code: ClassVar[str] = "CONFIG_ERROR"
    retryable: ClassVar[bool] = False


class ValidationError(AppError):
    code: ClassVar[str] = "VALIDATION_ERROR"
    retryable: ClassVar[bool] = False


class NotFoundError(AppError):
    code: ClassVar[str] = "NOT_FOUND"
    retryable: ClassVar[bool] = False


class ConflictError(AppError):
    code: ClassVar[str] = "CONFLICT"
    retryable: ClassVar[bool] = False


class DependencyError(AppError):
    code: ClassVar[str] = "DEPENDENCY_ERROR"
    retryable: ClassVar[bool] = True


class TimeoutError_(AppError):
    code: ClassVar[str] = "TIMEOUT"
    retryable: ClassVar[bool] = True


class LimitExceededError(AppError):
    code: ClassVar[str] = "LIMIT_EXCEEDED"
    retryable: ClassVar[bool] = False


class NumericalError(AppError):
    code: ClassVar[str] = "NUMERICAL_ERROR"
    retryable: ClassVar[bool] = False


class PermissionDeniedError(AppError):
    code: ClassVar[str] = "PERMISSION_DENIED"
    retryable: ClassVar[bool] = False
