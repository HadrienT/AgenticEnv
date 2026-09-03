from __future__ import annotations

from corelib.errors import ConfigError, DependencyError


class IndexUnavailableError(DependencyError):
    """No usable index for this project (I4): missing `compile_commands.json`.

    Retryable: the caller can run `cpp.configure` and try again.
    """


class ClangdCrashedError(DependencyError):
    """The `clangd` subprocess exited or failed to answer before the tool timeout."""


class ClangdNotFoundError(ConfigError):
    """The `clangd` binary is not on `PATH`. Never falls back to `grep` (I4)."""


class ProjectDiscoveryError(ConfigError):
    """`root` or the resolved build directory don't look like a valid C++ project."""
