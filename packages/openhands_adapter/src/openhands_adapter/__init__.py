"""openhands_adapter: OpenHands SDK sandbox driving the local llama-server.

Docker agent-server isolation for OpenHands (WP08 phase 2, see
blueprint/wp/WP08b-openhands-sandbox.md) -- complements WP08's CLI-headless
integration, which deliberately runs without a sandbox.
"""

from __future__ import annotations

# Re-exported so that other in-repo packages (e.g. openhands_bridge) never need
# their own `import openhands.*` -- this package is the one place allowed to
# depend on the SDK directly (import-linter contract D14 in the root
# pyproject.toml). Keep this list to what callers genuinely need.
from openhands.sdk import Event
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from openhands.sdk.security.confirmation_policy import (
    AlwaysConfirm,
    ConfirmationPolicyBase,
    ConfirmRisky,
    NeverConfirm,
)

from openhands_adapter.config import OpenHandsConfig, load_openhands_config
from openhands_adapter.docker_workspace import AgenticEnvDockerWorkspace
from openhands_adapter.session import AgentResult, AgentSession, run_task

__all__ = [
    "AgentResult",
    "AgentSession",
    "AgenticEnvDockerWorkspace",
    "AlwaysConfirm",
    "ConfirmRisky",
    "ConfirmationPolicyBase",
    "ConversationStateUpdateEvent",
    "Event",
    "NeverConfirm",
    "OpenHandsConfig",
    "load_openhands_config",
    "run_task",
]
