"""qmharness-specific error taxonomy, all rooted in `corelib.errors.AppError`
(blueprint/07-ERRORS-AND-LOGGING.md §2)."""

from __future__ import annotations

from corelib.errors import ConfigError, DependencyError, ValidationError


class CaseValidationError(ValidationError):
    """A case (YAML entry or a family dispatch) is malformed. Never silently skipped
    (WP09 §10: "cas malformé => ValidationError explicite")."""


class BuildNotComparableError(ValidationError):
    """`qm.compare` refuses: baseline/candidate build fingerprints disagree (WP09 §8)."""


class ModuleFingerprintError(DependencyError):
    """Could not determine the built `quantmodeling` module's commit/compiler/hash."""


class ExternalOracleUnavailableError(ConfigError):
    """The optional external oracle (e.g. QuantLib) is not installed; test-only dependency."""
