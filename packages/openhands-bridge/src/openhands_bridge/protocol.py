"""WebSocket wire protocol between the bridge and a chat client (e.g. the
`agenticenv-chat` VS Code extension).

Deliberately decoupled from `openhands.sdk` types: the wire format is a small,
stable contract of our own, translated to/from SDK objects in `server.py`. That
keeps the SDK's own (larger, faster-moving) schemas out of the client's concern,
and matches `openhands_bridge` NOT being one of the packages allowed to import
`openhands.*` -- see blueprint/wp/WP08b-openhands-sandbox.md and the
import-linter contract for `openhands_adapter` in the root `pyproject.toml`.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from corelib.errors import ValidationError
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# --- client -> bridge --------------------------------------------------------


class StartSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["start_session"] = "start_session"
    # Names from configs/mcp/*.yaml the user checked in the pre-session picker.
    # Phase 1: accepted and stored, not yet wired into a working sandbox MCP
    # connection -- see WP08b-openhands-sandbox.md §7 (deferred to Phase 2).
    mcp_servers: list[str] = Field(default_factory=list)
    # Host directory to bind-mount into the sandbox and run the agent in
    # (typically the client's open workspace folder). None -> empty /workspace.
    project_path: str | None = None


class UserMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["user_message"] = "user_message"
    text: str


class ConfirmAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["confirm_action"] = "confirm_action"
    accept: bool


class ListMcpServers(BaseModel):
    """Ask for the catalog of configured MCP servers (for the pre-session picker).
    Valid with or without an active session; has no side effects."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["list_mcp_servers"] = "list_mcp_servers"


InboundMessage = Annotated[
    StartSession | UserMessage | ConfirmAction | ListMcpServers, Field(discriminator="type")
]
_inbound_adapter: TypeAdapter[InboundMessage] = TypeAdapter(InboundMessage)


def parse_inbound(raw: str | bytes) -> InboundMessage:
    try:
        return _inbound_adapter.validate_json(raw)
    except Exception as exc:  # noqa: BLE001 - re-raised as a typed AppError below
        raise ValidationError(f"invalid message from client: {exc}") from exc


# --- bridge -> client ---------------------------------------------------------


class SessionStarted(BaseModel):
    type: Literal["session_started"] = "session_started"
    conversation_id: str
    llm_source: str


class EventMessage(BaseModel):
    """One `openhands.sdk.event.Event`, already serialized (`model_dump(mode="json")`)."""

    type: Literal["event"] = "event"
    event: dict[str, Any]


class GitChangeDTO(BaseModel):
    status: Literal["ADDED", "DELETED", "UPDATED", "MOVED"]
    path: str


class FilesChanged(BaseModel):
    type: Literal["files_changed"] = "files_changed"
    changes: list[GitChangeDTO]


class Usage(BaseModel):
    type: Literal["usage"] = "usage"
    accumulated_cost: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # 0 means "unknown" (llama-server / a custom LLM entry may not report one).
    context_window: int = 0


class AwaitingConfirmation(BaseModel):
    type: Literal["awaiting_confirmation"] = "awaiting_confirmation"
    conversation_id: str


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class McpServerEntry(BaseModel):
    name: str
    transport: str
    tools_allowlist: list[str] = Field(default_factory=list)


class McpServers(BaseModel):
    type: Literal["mcp_servers"] = "mcp_servers"
    servers: list[McpServerEntry]


OutboundMessage = (
    SessionStarted
    | EventMessage
    | FilesChanged
    | Usage
    | AwaitingConfirmation
    | ErrorMessage
    | McpServers
)


def serialize_outbound(message: OutboundMessage) -> str:
    return message.model_dump_json()
