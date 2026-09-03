from __future__ import annotations

from corelib.errors import ConfigError


class ToolMissingError(ConfigError):
    """An external toolchain binary (ninja, clang-tidy, gcovr…) is not on `PATH`."""


class ProjectDiscoveryError(ConfigError):
    """`CMakePresets.json` is missing, unreadable, or names an unknown preset."""
