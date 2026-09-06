"""WebSocket wire protocol between the bridge and a chat client (the
`agenticenv-chat` VS Code extension).

Source of truth is `agenticenv-chat/src/protocol.ts` -- this file is its manual
mirror (cross-repo drift test on the client side). Deliberately decoupled from
`openhands.sdk` types: the wire format is our own small contract, translated
to/from SDK objects in `server.py`, and `openhands_bridge` never imports
`openhands.*` (import-linter contract D15).

Protocol v2 (agenticenv-chat/docs/bridge-v2-spec.md): `hello`/`welcome`
negotiation, a monotonic `seq` on every outbound message, turn boundaries,
cancellation, mid-turn context stats, and -- for WP08d -- a disposable sandbox
working copy with `apply_changes` back to the real repo. Capabilities the
bridge does NOT implement yet (deltas, todo, compact, interrupt, models,
resume) are simply not announced; the client degrades per capability.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from corelib.errors import ValidationError
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

PROTOCOL_VERSION = 2

# Capabilities this bridge announces in `welcome`. Announce ONLY what is
# implemented and tested (spec §1). WP08d adds `apply` (not in the spec's
# original list -- added to protocol.ts in the same cross-repo change).
CAPABILITIES: tuple[str, ...] = ("turns", "cancel", "diffs", "checkpoints", "apply")

_MAX_PAYLOAD_BYTES = 256 * 1024  # spec §3: truncate larger payloads

# --- client -> bridge --------------------------------------------------------


class Hello(BaseModel):
    """First message of every connection (spec §1). Until the bridge accepts
    this, the v1 rejection makes the client degrade silently."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["hello"] = "hello"
    protocol: int
    client: str


class ResolvedContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str
    label: str
    body: str
    truncated: bool = False


class StartSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["start_session"] = "start_session"
    mcp_servers: list[str] = Field(default_factory=list)
    # Host directory bind-mounted READ-ONLY into the sandbox; the agent works on
    # a disposable copy of it (WP08d). None -> empty /workspace.
    project_path: str | None = None
    # "agent" (default) allows apply_changes; "read_only" (Ask / Plan modes)
    # refuses it -- the agent may still experiment in the throwaway copy.
    mode: Literal["agent", "read_only"] = "agent"


class UserMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["user_message"] = "user_message"
    text: str
    # v2 (spec §5.1): the host resolves #-references and passes them here instead
    # of concatenating into `text`. The bridge presents them to the model.
    context: list[ResolvedContext] = Field(default_factory=list)


class ConfirmAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["confirm_action"] = "confirm_action"
    accept: bool
    # v2 best-effort fields (spec §5); currently informational.
    action_id: str | None = None
    remember: Literal["session", "workspace"] | None = None
    edited_command: str | None = None


class CancelTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["cancel_turn"] = "cancel_turn"
    turn_id: str


class ListMcpServers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["list_mcp_servers"] = "list_mcp_servers"


class RequestDiff(BaseModel):
    """Unified diff (session baseline -> now) of one file in the sandbox copy."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["request_diff"] = "request_diff"
    path: str


class RequestBundleDiff(BaseModel):
    """Unified diff of every changed file in the sandbox copy (WP08d)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["request_bundle_diff"] = "request_bundle_diff"


class RestoreCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["restore_checkpoint"] = "restore_checkpoint"
    checkpoint_id: str


class ApplyChanges(BaseModel):
    """Write changed files from the sandbox copy into the real host repo (WP08d).
    `paths` absent -> all changed files. `force` overrides conflict detection."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["apply_changes"] = "apply_changes"
    paths: list[str] | None = None
    force: bool = False


class DiscardChanges(BaseModel):
    """Reset files in the sandbox copy back to the session baseline (WP08d)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["discard_changes"] = "discard_changes"
    paths: list[str] | None = None


InboundMessage = Annotated[
    Hello
    | StartSession
    | UserMessage
    | ConfirmAction
    | CancelTurn
    | ListMcpServers
    | RequestDiff
    | RequestBundleDiff
    | RestoreCheckpoint
    | ApplyChanges
    | DiscardChanges,
    Field(discriminator="type"),
]
_inbound_adapter: TypeAdapter[InboundMessage] = TypeAdapter(InboundMessage)


def parse_inbound(raw: str | bytes) -> InboundMessage:
    try:
        return _inbound_adapter.validate_json(raw)
    except Exception as exc:  # noqa: BLE001 - re-raised as a typed AppError below
        raise ValidationError(f"invalid message from client: {exc}") from exc


# --- bridge -> client -------------------------------------------------------
#
# Every outbound message carries a monotonic `seq` (spec §2), stamped centrally
# in `server.py` right before send. It defaults to None here so models can be
# constructed without one in tests.


class _Out(BaseModel):
    seq: int | None = None


class Welcome(_Out):
    type: Literal["welcome"] = "welcome"
    protocol: int = PROTOCOL_VERSION
    capabilities: list[str] = Field(default_factory=lambda: list(CAPABILITIES))


class SessionStarted(_Out):
    type: Literal["session_started"] = "session_started"
    conversation_id: str
    llm_source: str
    mode: Literal["agent", "read_only"] = "agent"


class EventMessage(_Out):
    """One `openhands.sdk.event.Event`, already serialized (`model_dump(mode="json")`)."""

    type: Literal["event"] = "event"
    event: dict[str, Any]


class TurnStarted(_Out):
    type: Literal["turn_started"] = "turn_started"
    turn_id: str


TurnFinishedReason = Literal["completed", "cancelled", "error", "max_iterations"]


class TurnFinished(_Out):
    type: Literal["turn_finished"] = "turn_finished"
    turn_id: str
    reason: TurnFinishedReason


class ToolStatus(_Out):
    type: Literal["tool_status"] = "tool_status"
    tool_call_id: str
    state: Literal["running", "ok", "error"]
    label: str | None = None


class Progress(_Out):
    type: Literal["progress"] = "progress"
    turn_id: str
    label: str


class ContextStats(_Out):
    type: Literal["context_stats"] = "context_stats"
    prompt_tokens: int = 0
    context_window: int = 0
    compacted: bool = False


class GitChangeDTO(BaseModel):
    status: Literal["ADDED", "DELETED", "UPDATED", "MOVED"]
    path: str


class FilesChanged(_Out):
    type: Literal["files_changed"] = "files_changed"
    changes: list[GitChangeDTO]


class FileDiffMessage(_Out):
    type: Literal["file_diff"] = "file_diff"
    path: str
    unified: str
    truncated: bool = False


class BundleDiffMessage(_Out):
    type: Literal["bundle_diff"] = "bundle_diff"
    unified: str
    truncated: bool = False


class CheckpointMessage(_Out):
    type: Literal["checkpoint"] = "checkpoint"
    checkpoint_id: str
    turn_id: str
    created_at: str
    files: list[str] = Field(default_factory=list)


class CheckpointRestored(_Out):
    type: Literal["checkpoint_restored"] = "checkpoint_restored"
    checkpoint_id: str


class AppliedEntry(BaseModel):
    path: str
    status: Literal["ADDED", "DELETED", "UPDATED", "MOVED"]


class SkippedEntry(BaseModel):
    path: str
    reason: str


class ChangesApplied(_Out):
    type: Literal["changes_applied"] = "changes_applied"
    applied: list[AppliedEntry] = Field(default_factory=list)
    skipped: list[SkippedEntry] = Field(default_factory=list)


class Usage(_Out):
    type: Literal["usage"] = "usage"
    accumulated_cost: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    context_window: int = 0


class AwaitingConfirmation(_Out):
    type: Literal["awaiting_confirmation"] = "awaiting_confirmation"
    conversation_id: str


class ErrorMessage(_Out):
    type: Literal["error"] = "error"
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class McpServerEntry(BaseModel):
    name: str
    transport: str
    tools_allowlist: list[str] = Field(default_factory=list)


class McpServers(_Out):
    type: Literal["mcp_servers"] = "mcp_servers"
    servers: list[McpServerEntry]


OutboundMessage = (
    Welcome
    | SessionStarted
    | EventMessage
    | TurnStarted
    | TurnFinished
    | ToolStatus
    | Progress
    | ContextStats
    | FilesChanged
    | FileDiffMessage
    | BundleDiffMessage
    | CheckpointMessage
    | CheckpointRestored
    | ChangesApplied
    | Usage
    | AwaitingConfirmation
    | ErrorMessage
    | McpServers
)


def serialize_outbound(message: OutboundMessage) -> str:
    return message.model_dump_json()


def truncate(text: str) -> tuple[str, bool]:
    """Clip an oversized payload (spec §3: > 256 KiB)."""
    encoded = text.encode("utf-8")
    if len(encoded) <= _MAX_PAYLOAD_BYTES:
        return text, False
    return encoded[:_MAX_PAYLOAD_BYTES].decode("utf-8", errors="ignore"), True
