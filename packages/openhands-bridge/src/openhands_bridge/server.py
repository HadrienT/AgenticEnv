"""WebSocket server: one bridge process, at most one `AgentSession` at a time.

Protocol v2 (agenticenv-chat/docs/bridge-v2-spec.md) + WP08d (the disposable
sandbox working copy). Every connection opens with `hello`/`welcome`
capability negotiation; every outbound message carries a monotonic `seq`;
each user message is wrapped in `turn_started`/`turn_finished`, can be
cancelled mid-flight, and -- when the session has a project working copy --
is preceded by a `checkpoint` the client can restore. At the end of each turn
the agent's edits are written from the throwaway copy back into the real host
repo (WP08g), by *this* process (which runs as the user, unlike the uid-10001
agent-server); restoring a checkpoint goes through the same sync, so an undo
reaches the real repo too. A `read_only` session never writes.

Connections themselves are never gated -- a client may connect, negotiate,
list MCP servers, and reconnect freely (VS Code restarts its extension host,
dropping and reopening the socket). Only creating a second concurrent
`AgentSession` (a second Docker sandbox) is refused, with `SESSION_BUSY`,
without closing the connection.

Concurrency: a turn runs in its own task, so the read loop stays free for
`cancel_turn`, diffs and a disconnect (WP11). The run is triggered non-blocking
(`session.send(blocking=False)` in a worker thread) and the turn's terminal
status is awaited on the event loop -- watching the SDK's own
`ConversationStateUpdateEvent` callbacks (fired from the SDK's internal
websocket-listener thread) with a REST poll as a fallback. `cancel_turn` rejects
any pending action and calls `conversation.pause()`, moving the run to a
terminal/`paused` state the same watcher observes and reports as a cancelled
turn, within `_CANCEL_GRACE_S` even if the agent-server never confirms.

The confirmation policy is `NeverConfirm` (WP08d): the agent works on a
disposable copy and acts without per-action prompts. `waiting_for_confirmation`
should not occur; if it ever does, the turn watcher still bounds the wait by
`run_timeout_s` rather than hanging.

With `sandbox.persistent_conversations` (WP08e), a sandbox outlives its connection:
it holds several conversations of one project, one active at a time, and closes
`_SANDBOX_IDLE_S` after its client left. `resume` reattaches to a conversation, in
this sandbox or in a new one if the bridge restarted, and replays what the client
missed. Off, a session ends with its connection, as described above.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from corelib.errors import AppError
from corelib.logging import get_logger
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from openhands_adapter import (
    DEFAULT_PROFILE,
    STARTUP_STEPS,
    STEP_BASELINE,
    STEP_CHECKS,
    ActionEvent,
    AgentSession,
    ConversationStateUpdateEvent,
    Event,
    GitChange,
    MessageEvent,
    NeverConfirm,
    StreamingDeltaEvent,
    list_profiles,
    load_openhands_config,
    reap_orphan_sandboxes,
)
from openhands_bridge import apply as apply_mod
from openhands_bridge import conversations, memory
from openhands_bridge import models as models_mod
from openhands_bridge.auth import ensure_token, serve_options, validate_project_path
from openhands_bridge.mcp_catalog import build_mcp_config, list_mcp_servers, unavailable_reason
from openhands_bridge.protocol import (
    CAPABILITIES,
    AppliedEntry,
    ApplyChanges,
    ArchiveConversation,
    AwaitingConfirmation,
    BundleDiffMessage,
    CancelTurn,
    ChangesApplied,
    CheckpointMessage,
    CheckpointRestored,
    Compact,
    ConfirmAction,
    ContextStats,
    ConversationItem,
    Conversations,
    ErrorMessage,
    EventDelta,
    EventMessage,
    FileDiffMessage,
    FilesChanged,
    GitChangeDTO,
    Hello,
    HistoryCompacted,
    InboundMessage,
    Interrupt,
    ListConversations,
    ListMcpServers,
    ListModels,
    McpServerEntry,
    McpServers,
    Models,
    OutboundMessage,
    RequestBundleDiff,
    RequestDiff,
    RestoreCheckpoint,
    Resume,
    Resumed,
    SessionProgress,
    SessionStarted,
    SetModel,
    SkippedEntry,
    StartSession,
    TodoItem,
    TodoMessage,
    TurnFinished,
    TurnFinishedReason,
    TurnStarted,
    Usage,
    UserDisplay,
    UserMessage,
    Welcome,
    parse_inbound,
    serialize_outbound,
    truncate,
)

logger = get_logger(__name__)

_DEFAULT_PORT = 8300
_DEFAULT_HOST = "127.0.0.1"

# Statuses that end a turn's wait. `paused` is here because `cancel_turn`
# resolves through `conversation.pause()`; `waiting_for_confirmation` is
# deliberately absent -- that turn is still live, waiting on the user.
_TERMINAL_TURN_STATUSES = frozenset({"finished", "error", "stuck", "paused"})

_TODO_STATES: dict[str, Literal["pending", "active", "done"]] = {
    "todo": "pending",
    "in_progress": "active",
    "done": "done",
}

# Agent-server internals that live under the sandbox workspace and must never be
# shown as "the agent changed this file in your project".
_INTERNAL_PREFIXES = ("conversations/", ".git/", ".openhands/")
_INTERNAL_NAMES = {"owner_lease.json", "meta.json"}
# If `git_changes` returns more than this, the working dir almost certainly is
# not a git repo and the agent-server listed every file -- send nothing rather
# than a wall of noise.
_MAX_REPORTED_CHANGES = 200
# How long a stopped run may take to report it, and how long the agent-server may
# take to accept the stop itself, before the bridge moves on regardless.
_CANCEL_GRACE_S = 30.0
_STOP_CALL_TIMEOUT_S = 10.0
_DISCONNECT_SYNC_TIMEOUT_S = 60.0
_RECALL_TIMEOUT_S = 10.0
# How much a client can catch up on, and how long a sandbox waits for it to come back.
_REPLAY_LIMIT = 2000
_SANDBOX_IDLE_S = 900.0

# At most one *AgentSession* (= one Docker sandbox) at a time across the whole
# process, but connections are NOT gated. `_session_owner` is the connection
# that currently owns the active session; the guard is held only briefly
# around create/teardown, never for a connection's lifetime.
_session_guard = asyncio.Lock()
_background_tasks: set[asyncio.Task[str | None]] = set()
_session_owner: _Connection | None = None
_sandbox: _Sandbox | None = None


@dataclass
class _ConversationState:
    """What a connection works with, kept while the conversation is not the active one."""

    conversation_id: str
    seq: int = 0
    replay: deque[tuple[int, str]] = field(default_factory=lambda: deque(maxlen=_REPLAY_LIMIT))
    baseline_hashes: dict[str, str] = field(default_factory=dict)
    conflicts: set[str] = field(default_factory=set)
    draft: memory.SessionDraft | None = None


@dataclass
class _Sandbox:
    """The long-lived sandbox: one project, in one mode, with one set of tools."""

    session: AgentSession
    key: tuple[object, ...]
    states: dict[str, _ConversationState] = field(default_factory=dict)
    idle_task: asyncio.Task[None] | None = None


def _forward_event(event: Event) -> None:
    """A sandbox outlives connections, so its callback follows whichever one owns it."""
    owner = _session_owner
    if owner is not None:
        owner.relay.on_event(event)


def _sandbox_key(request: StartSession) -> tuple[object, ...]:
    return (request.project_path, request.mode, request.profile, tuple(request.mcp_servers))


def _persistent() -> bool:
    return load_openhands_config().sandbox.persistent_conversations


def _error_from(exc: AppError) -> ErrorMessage:
    return ErrorMessage(code=exc.code, message=exc.message, details=dict(exc.details))


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _todo_items(event: Event) -> list[TodoItem] | None:
    """The agent's `task_tracker` list, when `event` is one of its results."""
    tasks = getattr(getattr(event, "observation", None), "task_list", None)
    if getattr(event, "tool_name", None) != "task_tracker" or tasks is None:
        return None
    return [
        TodoItem(id=str(index), text=task.title, state=_TODO_STATES.get(task.status, "pending"))
        for index, task in enumerate(tasks)
    ]


class _EventRelay:
    """Forwards `Event` callbacks to the client, buffering anything fired
    before the client has been sent `session_started`.

    `AgentSession.__enter__` starts the SDK's own WebSocket listener thread as
    part of creating the conversation, and that thread can fire callbacks
    (e.g. the initial state snapshot) *before* `_start_session` sends
    `session_started` -- observed in `test_bridge_e2e.py`. Buffering here, then
    flushing right after `session_started`, keeps the ordering guarantee simple
    for the client. Execution-status updates are still fed to the connection's
    turn watcher while buffering, so a fast terminal status is never missed.
    """

    def __init__(self, conn: _Connection) -> None:
        self._conn = conn
        self._lock = threading.Lock()
        self._buffering = True
        # Replaces the next user echo, whose text is the whole composed prompt.
        self.user_display: UserDisplay | None = None
        # Deltas carry no event id of their own: this ties them to the event that
        # ends them, the agent's message or the action they narrate.
        self._stream_id: str | None = None
        self._buffer: list[Event] = []
        self.session: AgentSession | None = None

    def on_event(self, event: Event) -> None:
        if (
            isinstance(event, ConversationStateUpdateEvent)
            and event.key == "execution_status"
            and isinstance(event.value, str)
        ):
            self._conn.note_status_threadsafe(event.value)
        with self._lock:
            if self._buffering:
                self._buffer.append(event)
                return
        self._dispatch(event)

    def _dispatch(self, event: Event) -> None:
        turn_id = self._conn.turn_id
        display = None
        if isinstance(event, MessageEvent) and event.source == "user":
            display, self.user_display = self.user_display, None
        if isinstance(event, StreamingDeltaEvent):
            if event.content and turn_id:
                self._stream_id = self._stream_id or uuid.uuid4().hex
                self._conn.send_threadsafe(
                    EventDelta(turn_id=turn_id, event_id=self._stream_id, text=event.content)
                )
            return
        stream_id = None
        if isinstance(event, ActionEvent) or (
            isinstance(event, MessageEvent) and event.source == "agent"
        ):
            stream_id, self._stream_id = self._stream_id, None
        self._conn.send_threadsafe(
            EventMessage(
                event=event.model_dump(mode="json"), user_display=display, stream_id=stream_id
            )
        )
        todo = _todo_items(event)
        if todo is not None:
            self._conn.send_threadsafe(TodoMessage(items=todo))
        if (
            isinstance(event, ConversationStateUpdateEvent)
            and event.key == "execution_status"
            and event.value == "waiting_for_confirmation"
            and self.session is not None
        ):
            self._conn.send_threadsafe(
                AwaitingConfirmation(conversation_id=str(self.session.conversation.id))
            )

    async def release(self, session: AgentSession) -> None:
        """Call once `session_started` has actually been sent."""
        self.session = session
        with self._lock:
            buffered, self._buffer = self._buffer, []
            self._buffering = False
        for event in buffered:
            self._dispatch(event)


class _Connection:
    """Per-connection state: the `seq` counter, the (at most one) session it
    owns, and the currently running turn."""

    def __init__(self, ws: ServerConnection, loop: asyncio.AbstractEventLoop) -> None:
        self.ws = ws
        self.loop = loop
        self.client_id: str | None = None
        self.protocol = 1
        self.relay = _EventRelay(self)
        self.session: AgentSession | None = None
        self.turn_id: str | None = None
        self.cancelled = False
        self.cancel_deadline: float | None = None
        self.turn_task: asyncio.Task[None] | None = None
        self.baseline_hashes: dict[str, str] = {}
        self.conflicts: set[str] = set()
        self.draft: memory.SessionDraft | None = None
        self.state: _ConversationState | None = None
        self._seq = 0
        self._send_lock = asyncio.Lock()
        self._turn_terminal = asyncio.Event()
        self._last_status = "idle"

    async def send(self, message: OutboundMessage) -> None:
        # The lock makes `seq` assignment and the wire write one step, so the
        # sequence numbers a client sees always match delivery order even when
        # sends race between the event loop and the SDK callback thread.
        async with self._send_lock:
            self._seq += 1
            message.seq = self._seq
            raw = serialize_outbound(message)
            # Deltas are left out: the event that ends them carries the whole text.
            if self.state is not None and not isinstance(message, EventDelta):
                self.state.replay.append((self._seq, raw))
            with contextlib.suppress(ConnectionClosed):
                await self.ws.send(raw)

    def send_threadsafe(self, message: OutboundMessage) -> None:
        asyncio.run_coroutine_threadsafe(self.send(message), self.loop)

    def note_status_threadsafe(self, value: str) -> None:
        def _apply() -> None:
            self._last_status = value
            if value in _TERMINAL_TURN_STATUSES:
                self._turn_terminal.set()

        self.loop.call_soon_threadsafe(_apply)

    def bind(self, state: _ConversationState) -> None:
        self.unbind()
        self.state = state
        self._seq = state.seq
        self.baseline_hashes = state.baseline_hashes
        self.conflicts = state.conflicts
        self.draft = state.draft

    def unbind(self) -> None:
        state, self.state = self.state, None
        if state is not None:
            state.seq = self._seq
            state.baseline_hashes = self.baseline_hashes
            state.conflicts = self.conflicts
            state.draft = self.draft


async def _handle_connection(ws: ServerConnection) -> None:
    loop = asyncio.get_running_loop()
    conn = _Connection(ws, loop)
    try:
        async for raw in ws:
            try:
                inbound = parse_inbound(raw)
            except AppError as exc:
                await conn.send(_error_from(exc))
                continue
            try:
                await _dispatch_inbound(conn, inbound)
            except AppError as exc:
                await conn.send(_error_from(exc))
            except Exception as exc:  # noqa: BLE001 - one bad message must not kill the session
                logger.exception("unhandled error on %s", type(inbound).__name__)
                await conn.send(ErrorMessage(code="INTERNAL_ERROR", message=str(exc)))
    finally:
        await _end_running_turn(conn)
        await _close_draft(conn)
        if _sandbox is not None and conn.session is _sandbox.session:
            await _release_sandbox(conn)
        else:
            await _end_session(conn)


async def _end_session(conn: _Connection) -> None:
    global _session_owner
    if conn.session is not None:
        try:
            await asyncio.to_thread(conn.session.__exit__, None, None, None)
        except Exception:  # noqa: BLE001 - ownership below must still be released
            logger.warning("session teardown failed", exc_info=True)
    _record_in_background(conn.draft)
    async with _session_guard:
        if _session_owner is conn:
            _session_owner = None
        no_active_session = _session_owner is None and _sandbox is None
    if no_active_session:
        # The session's own teardown normally removes its container (--rm);
        # sweep here too in case __exit__ failed, and pick up anything a
        # previous bridge process leaked. One container at a time (issue #8).
        reaped = await asyncio.to_thread(reap_orphan_sandboxes, None)
        if reaped:
            logger.info("reaped orphan sandbox containers", extra={"containers": reaped})


async def _dispatch_inbound(conn: _Connection, inbound: InboundMessage) -> None:
    global _session_owner

    if isinstance(inbound, Hello):
        conn.client_id = inbound.client
        conn.protocol = inbound.protocol
        await conn.send(Welcome(capabilities=_capabilities()))
        return

    if isinstance(inbound, ListModels):
        await conn.send(Models(models=await asyncio.to_thread(models_mod.list_models)))
        return

    if isinstance(inbound, SetModel):
        if conn.session is not None:
            await conn.send(
                ErrorMessage(
                    code="SESSION_ACTIVE", message="End the session before switching the model."
                )
            )
            return
        await models_mod.switch_model(inbound.model_id)
        await conn.send(Models(models=await asyncio.to_thread(models_mod.list_models)))
        return

    if isinstance(inbound, ListMcpServers):
        servers = await asyncio.to_thread(list_mcp_servers)
        config = load_openhands_config()
        await conn.send(
            McpServers(
                servers=[
                    McpServerEntry(
                        name=s.name,
                        transport=s.transport,
                        tools_allowlist=s.tools_allowlist,
                        unavailable=unavailable_reason(s, config),
                    )
                    for s in servers
                ],
                profiles=list_profiles(),
            )
        )
        return

    if isinstance(inbound, ListConversations):
        await conn.send(_conversation_list(conn))
        return

    if isinstance(inbound, ArchiveConversation):
        await _handle_archive(conn, inbound)
        return

    if isinstance(inbound, Resume):
        await _handle_resume(conn, inbound)
        return

    if isinstance(inbound, StartSession) and _persistent():
        await _enter_conversation(conn, inbound, None)
        return

    if isinstance(inbound, StartSession):
        if conn.session is not None:
            await conn.send(
                ErrorMessage(
                    code="ALREADY_STARTED",
                    message="This connection already has an active session.",
                )
            )
            return
        async with _session_guard:
            if _session_owner is not None:
                await conn.send(
                    ErrorMessage(
                        code="SESSION_BUSY",
                        message="A chat session is already active on this bridge.",
                    )
                )
                return
            _session_owner = conn
        if not await _start_session(conn, inbound):
            async with _session_guard:
                if _session_owner is conn:
                    _session_owner = None
        return

    if conn.session is None:
        await conn.send(ErrorMessage(code="NO_SESSION", message="Send start_session first."))
        return

    if isinstance(inbound, UserMessage | RestoreCheckpoint | ApplyChanges | Compact) and (
        conn.turn_task
    ):
        await conn.send(
            ErrorMessage(code="TURN_IN_PROGRESS", message="Wait for the running turn to finish.")
        )
    elif isinstance(inbound, UserMessage):
        conn.turn_task = asyncio.create_task(_handle_user_message(conn, inbound))
    elif isinstance(inbound, Compact):
        await _handle_compact(conn)
    elif isinstance(inbound, Interrupt):
        await _handle_interrupt(conn, inbound)
    elif isinstance(inbound, CancelTurn):
        await _handle_cancel(conn, inbound)
    elif isinstance(inbound, ConfirmAction):
        await _handle_confirm_action(conn, inbound)
    elif isinstance(inbound, RequestDiff):
        await _handle_request_diff(conn, inbound)
    elif isinstance(inbound, RequestBundleDiff):
        await _handle_request_bundle_diff(conn)
    elif isinstance(inbound, RestoreCheckpoint):
        await _handle_restore_checkpoint(conn, inbound)
    elif isinstance(inbound, ApplyChanges):
        await _handle_apply_changes(conn, inbound)


def _conversation_list(conn: _Connection) -> Conversations:
    active = conn.state.conversation_id if conn.state is not None else None
    return Conversations(
        items=[
            ConversationItem(
                conversation_id=record.conversation_id,
                title=record.title,
                updated_at=record.updated_at,
                turns=record.turns,
                active=record.conversation_id == active,
            )
            for record in conversations.listed()
        ]
    )


async def _handle_archive(conn: _Connection, message: ArchiveConversation) -> None:
    if conn.state is not None and conn.state.conversation_id == message.conversation_id:
        await conn.send(
            ErrorMessage(code="CONVERSATION_ACTIVE", message="Switch away from it first.")
        )
        return
    if not conversations.archive(message.conversation_id):
        await conn.send(_unknown_conversation(message.conversation_id))
        return
    state = _sandbox.states.get(message.conversation_id) if _sandbox is not None else None
    if state is not None:
        _record_in_background(state.draft)
        state.draft = None
    await conn.send(_conversation_list(conn))


def _unknown_conversation(conversation_id: str) -> ErrorMessage:
    return ErrorMessage(
        code="UNKNOWN_CONVERSATION",
        message="This bridge does not know that conversation.",
        details={"conversation_id": conversation_id},
    )


async def _handle_resume(conn: _Connection, message: Resume) -> None:
    record = conversations.get(message.conversation_id) if _persistent() else None
    if record is None:
        await conn.send(_unknown_conversation(message.conversation_id))
        return
    request = StartSession(
        mcp_servers=record.mcp_servers,
        project_path=record.project_path,
        profile=record.profile,
        mode="read_only" if record.mode == "read_only" else "agent",
    )
    if not await _enter_conversation(conn, request, record):
        return
    assert conn.state is not None
    for seq, raw in list(conn.state.replay):
        if seq > message.last_seq:
            with contextlib.suppress(ConnectionClosed):
                await conn.ws.send(raw)
    await conn.send(Resumed())


async def _enter_conversation(
    conn: _Connection, request: StartSession, record: conversations.ConversationRecord | None
) -> bool:
    """Gets `conn` onto a conversation, of the sandbox in place when it fits. Without a
    `record` the conversation is a new one. One active at a time: the running turn ends."""
    global _session_owner
    if conn.turn_id is not None:
        await _handle_cancel(conn, CancelTurn(turn_id=conn.turn_id))
    if conn.turn_task is not None:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await conn.turn_task
    await _close_draft(conn)

    key = _sandbox_key(request)
    async with _session_guard:
        if _session_owner is not None and _session_owner is not conn:
            await conn.send(
                ErrorMessage(
                    code="SESSION_BUSY",
                    message="A chat session is already active on this bridge.",
                )
            )
            return False
        _session_owner = conn
        if _sandbox is not None and _sandbox.key != key:
            conn.unbind()
            conn.session = None
            await _close_sandbox()

    conversation_id = record.conversation_id if record is not None else None
    if _sandbox is None:
        started = await _start_session(conn, request, conversation_id, seq=_seq_of(record))
        if not started:
            async with _session_guard:
                if _session_owner is conn:
                    _session_owner = None
        return started

    sandbox = _sandbox
    if sandbox.idle_task is not None:
        sandbox.idle_task.cancel()
        sandbox.idle_task = None
    conn.unbind()
    session = sandbox.session
    conn.session = session
    await conn.relay.release(session)
    opened = await asyncio.to_thread(session.open_conversation, conversation_id)
    state = sandbox.states.get(opened)
    if state is None:
        state = await _new_state(session, opened, request, _seq_of(record))
        sandbox.states[opened] = state
        _index_conversation(opened, request)
    conn.bind(state)
    if record is None:
        await conn.send(_session_started(session, request, [], []))
    return True


def _seq_of(record: conversations.ConversationRecord | None) -> int:
    return record.seq if record is not None else 0


def _index_conversation(conversation_id: str, request: StartSession) -> None:
    if conversations.get(conversation_id) is None:
        conversations.save(
            conversations.ConversationRecord(
                conversation_id=conversation_id,
                project_path=request.project_path,
                mode=request.mode,
                profile=request.profile,
                mcp_servers=request.mcp_servers,
            )
        )


async def _new_state(
    session: AgentSession, opened: str, request: StartSession, seq: int
) -> _ConversationState:
    state = _ConversationState(conversation_id=opened, seq=seq)
    if session.project_path is not None:
        state.baseline_hashes = await asyncio.to_thread(_snapshot_host_tree, session.project_path)
    if not session.read_only:
        state.draft = memory.SessionDraft(
            conversation_id=opened,
            profile=request.profile or DEFAULT_PROFILE,
            started_at=datetime.now(UTC),
            project=session.project_path.name if session.project_path else None,
        )
    return state


async def _release_sandbox(conn: _Connection) -> None:
    """The client left: the sandbox waits for it. Its conversations stay as they are."""
    global _session_owner
    conn.unbind()
    conn.session = None
    async with _session_guard:
        if _session_owner is conn:
            _session_owner = None
    assert _sandbox is not None
    _sandbox.idle_task = asyncio.create_task(_close_when_idle(_sandbox))


async def _close_when_idle(sandbox: _Sandbox) -> None:
    await asyncio.sleep(_SANDBOX_IDLE_S)
    async with _session_guard:
        if _sandbox is sandbox and _session_owner is None:
            await _close_sandbox()


async def _close_sandbox() -> None:
    """The caller holds the guard. Every conversation stays on disk, for `resume`."""
    global _sandbox
    sandbox, _sandbox = _sandbox, None
    if sandbox is None:
        return
    if sandbox.idle_task is not None and sandbox.idle_task is not asyncio.current_task():
        sandbox.idle_task.cancel()
    try:
        await asyncio.to_thread(sandbox.session.__exit__, None, None, None)
    except Exception:  # noqa: BLE001 - the sandbox is gone for the bridge either way
        logger.warning("sandbox teardown failed", exc_info=True)
    for state in sandbox.states.values():
        _record_in_background(state.draft)
    reaped = await asyncio.to_thread(reap_orphan_sandboxes, None)
    if reaped:
        logger.info("reaped orphan sandbox containers", extra={"containers": reaped})


def _session_started(
    session: AgentSession,
    request: StartSession,
    mcp_servers: list[str],
    mcp_unavailable: list[str],
) -> SessionStarted:
    return SessionStarted(
        conversation_id=str(session.conversation.id),
        llm_source=session.llm_source,
        mode="read_only" if session.read_only else "agent",
        copy_warnings=session.working_copy.copy_errors if session.working_copy else [],
        profile=request.profile or DEFAULT_PROFILE,
        mcp_servers=mcp_servers,
        mcp_unavailable=mcp_unavailable,
    )


async def _start_session(
    conn: _Connection,
    request: StartSession,
    conversation_id: str | None = None,
    *,
    seq: int = 0,
) -> bool:
    def report_step(step: int) -> None:
        conn.send_threadsafe(SessionProgress(steps=list(STARTUP_STEPS), current=step))

    report_step(STEP_CHECKS)
    # There is no active session, so any existing
    # agent-server-* container is an orphan -- clear it before spinning up a new
    # one so leaked sandboxes never pile up on a low-storage host.
    reaped = await asyncio.to_thread(reap_orphan_sandboxes, None)
    if reaped:
        logger.info("reaped orphan sandbox containers before start", extra={"containers": reaped})

    # NeverConfirm: the agent works on a disposable copy and a per-action
    # confirmation pause only wedges the turn (`ConfirmRisky` also adds a
    # security-analysis LLM call per action).
    try:
        project_path = validate_project_path(request.project_path) if request.project_path else None
        config = load_openhands_config()
        mcp_config, mcp_unavailable = await asyncio.to_thread(
            build_mcp_config, request.mcp_servers, config
        )
        profile = request.profile or DEFAULT_PROFILE
        persistent = config.sandbox.persistent_conversations
        session = AgentSession(
            oh_config=config,
            confirmation_policy=NeverConfirm(),
            callbacks=[_forward_event if persistent else conn.relay.on_event],
            project_path=project_path,
            read_only=request.mode == "read_only",
            mcp_config=mcp_config,
            profile=profile,
            on_step=report_step,
            persistent=persistent,
            conversation_id=conversation_id,
        )
        await asyncio.to_thread(session.__enter__)
    except AppError as exc:
        await conn.send(_error_from(exc))
        return False
    except Exception as exc:  # noqa: BLE001 - e.g. Docker refusing to start the container
        logger.exception("could not start the session")
        await conn.send(ErrorMessage(code="SESSION_START_FAILED", message=str(exc)))
        return False

    # Before `session_started`: an edit made once the client sees the session
    # must count as a conflict, not end up in the reference hashes.
    if session.project_path is not None:
        report_step(STEP_BASELINE)
    conn.session = session
    state = await _new_state(session, str(session.conversation.id), request, seq)
    if persistent:
        global _sandbox
        _sandbox = _Sandbox(session=session, key=_sandbox_key(request))
        _sandbox.states[state.conversation_id] = state
        conn.bind(state)
        _index_conversation(state.conversation_id, request)
    else:
        conn.baseline_hashes = state.baseline_hashes
        conn.draft = state.draft
    if conversation_id is None:
        await conn.send(
            _session_started(
                session,
                request,
                sorted(cast("dict[str, object]", mcp_config.get("mcpServers", {}))),
                mcp_unavailable,
            )
        )
    await conn.relay.release(session)
    return True


def _snapshot_host_tree(root: Path) -> dict[str, str]:
    """Content hashes of the real repo's tracked files at session start --
    the sync to the host compares against these to refuse a blind overwrite of
    a file the user edited meanwhile (WP08d conflict rule)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if proc.returncode == 0:
            rels = [p for p in proc.stdout.decode("utf-8", "ignore").split("\0") if p]
            return apply_mod.hash_host_tree(root, rels)
    except (OSError, subprocess.SubprocessError):
        logger.warning("could not list host tracked files; conflict detection degraded")
    rels = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
    return apply_mod.hash_host_tree(root, rels)


def _compose_prompt(message: UserMessage) -> str:
    """Prepend the host-resolved context blocks (spec §5.1) as tagged sections
    ahead of the user's text, rather than the client concatenating them in."""
    if not message.context:
        return message.text
    blocks = [
        f'<context source="{ctx.kind}" label="{ctx.label}"'
        f"{' truncated' if ctx.truncated else ''}>\n{ctx.body}\n</context>"
        for ctx in message.context
    ]
    return "\n\n".join([*blocks, message.text])


def _fire_run(session: AgentSession, text: str) -> None:
    session.send(text, blocking=False)


def _poll_status(session: AgentSession) -> str | None:
    try:
        info = session.conversation.state.refresh_from_server()
    except Exception:  # noqa: BLE001 - best-effort fallback; the WS path is primary
        return None
    status = info.get("execution_status")
    return status if isinstance(status, str) else None


async def _await_turn_terminal(conn: _Connection, session: AgentSession) -> str:
    """Wait for the running turn to reach a terminal status. Watches the SDK's
    status callbacks first, polls REST as a fallback. Bounded by
    `run_timeout_s` -- including a `waiting_for_confirmation` pause: with
    `NeverConfirm` that never happens, but if a confirmation ever appears with
    no client answering it, the turn must still end rather than hang forever.
    A timed-out run is stopped, not abandoned: it would keep editing the copy."""
    deadline = conn.loop.time() + session.run_timeout_s
    while True:
        try:
            await asyncio.wait_for(conn._turn_terminal.wait(), timeout=5.0)
            return conn._last_status
        except TimeoutError:
            status = _poll_status(session)
            if status in _TERMINAL_TURN_STATUSES:
                return status or "error"
            now = conn.loop.time()
            if conn.cancel_deadline is not None and now > conn.cancel_deadline:
                return "paused"
            if now > deadline:
                await _stop_agent(session)
                return "timeout"


async def _with_past_experience(prompt: str, text: str) -> str:
    try:
        context = await asyncio.wait_for(
            asyncio.to_thread(memory.recall_context, text), _RECALL_TIMEOUT_S
        )
    except TimeoutError:
        return prompt
    return f"{context}\n\n{prompt}" if context else prompt


async def _close_draft(conn: _Connection) -> None:
    """Reads the agent's last words while the sandbox is still up."""
    session = conn.session
    if conn.draft is None or session is None:
        return
    try:
        conn.draft.final_text = await asyncio.wait_for(
            asyncio.to_thread(session.final_text), _STOP_CALL_TIMEOUT_S
        )
        changes = await _current_changes(session)
        conn.draft.changed_files = [change.path for change in changes]
    except Exception:  # noqa: BLE001 - a thinner episode beats a failed teardown
        logger.info("could not read the end of the session", exc_info=True)


def _record_in_background(draft: memory.SessionDraft | None) -> None:
    """After the session is released: a slow summary must not keep it busy."""
    if draft is None or not draft.messages:
        return
    task = asyncio.create_task(
        asyncio.to_thread(memory.record_episode, draft, ended_at=datetime.now(UTC))
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _stop_agent(session: AgentSession) -> None:
    """`pause()` unwinds a running loop; `reject_pending_actions()` unblocks a turn
    parked at `waiting_for_confirmation` (where `pause()` is a no-op). Do both,
    each bounded: a hung agent-server must not hang the bridge with it."""
    conversation = session.conversation
    for call in (conversation.reject_pending_actions, conversation.pause):
        with contextlib.suppress(Exception):
            await asyncio.wait_for(asyncio.to_thread(call), _STOP_CALL_TIMEOUT_S)


async def _end_running_turn(conn: _Connection) -> None:
    """The client left mid-turn: stop the agent and keep what it did so far, since
    the copy goes away with the session."""
    task = conn.turn_task
    session = conn.session
    if task is None or session is None:
        return
    await _stop_agent(session)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task
    conn.turn_task = None
    conn.turn_id = None
    if _auto_applies(session):
        try:
            await asyncio.wait_for(_sync_to_host(conn, session), _DISCONNECT_SYNC_TIMEOUT_S)
        except Exception:  # noqa: BLE001 - teardown must carry on
            logger.warning("could not sync the working copy after a disconnect", exc_info=True)


def _reason_for(conn: _Connection, status: str) -> TurnFinishedReason:
    if conn.cancelled or status == "paused":
        return "cancelled"
    if status in ("error", "stuck", "timeout"):
        return "error"
    return "completed"


async def _handle_user_message(conn: _Connection, message: UserMessage) -> None:
    session = conn.session
    assert session is not None
    turn_id = uuid.uuid4().hex
    conn.turn_id = turn_id
    conn.cancelled = False
    conn.cancel_deadline = None
    conn._turn_terminal.clear()

    reason: TurnFinishedReason = "error"
    try:
        if session.working_copy is not None:
            checkpoint = await asyncio.to_thread(session.working_copy.checkpoint)
            if checkpoint is not None:
                await conn.send(
                    CheckpointMessage(
                        checkpoint_id=checkpoint.checkpoint_id,
                        turn_id=turn_id,
                        created_at=_utcnow(),
                        files=checkpoint.files,
                    )
                )

        await conn.send(TurnStarted(turn_id=turn_id))
        prompt = _compose_prompt(message)
        if _auto_applies(session):
            pulled = await _pull_from_host(conn, session)
            if pulled:
                note = f"<user_edits>Changed by the user since your last turn: {', '.join(pulled)}"
                prompt = f"{note}</user_edits>\n\n{prompt}"
        loaded = [ctx.label for ctx in message.context]
        draft = conn.draft
        if draft is not None:
            if not draft.messages:
                recalled = await _with_past_experience(prompt, message.text)
                if recalled != prompt:
                    loaded.append("past lessons")
                prompt = recalled
            draft.messages.append(message.text)
        if prompt != message.text:
            conn.relay.user_display = UserDisplay(text=message.text, loaded=loaded)
        await asyncio.to_thread(_fire_run, session, prompt)
        reason = _reason_for(conn, await _await_turn_terminal(conn, session))
    except AppError as exc:
        await conn.send(_error_from(exc))
    except Exception as exc:  # noqa: BLE001 - `turn_finished` must always follow
        logger.exception("turn failed")
        await conn.send(ErrorMessage(code="TURN_FAILED", message=str(exc)))

    if _auto_applies(session):
        try:
            await _sync_to_host(conn, session)
        except Exception as exc:  # noqa: BLE001 - the turn must still finish cleanly
            logger.warning("could not sync the working copy to the host", exc_info=True)
            await conn.send(ErrorMessage(code="APPLY_FAILED", message=str(exc)))

    try:
        await _emit_post_turn(conn)
    except Exception:  # noqa: BLE001 - stats are not worth losing `turn_finished` for
        logger.warning("could not report post-turn stats", exc_info=True)

    if conn.draft is not None:
        conn.draft.last_reason = reason
    conn.turn_id = None
    conn.turn_task = None
    await conn.send(TurnFinished(turn_id=turn_id, reason=reason))
    if conn.state is not None:
        conversations.note_turn(conn.state.conversation_id, message.text, conn._seq)


async def _handle_cancel(conn: _Connection, message: CancelTurn) -> None:
    if conn.turn_id != message.turn_id or conn.session is None:
        return
    conn.cancelled = True
    conn.cancel_deadline = conn.loop.time() + _CANCEL_GRACE_S
    await _stop_agent(conn.session)


async def _handle_compact(conn: _Connection) -> None:
    session = conn.session
    assert session is not None
    await asyncio.to_thread(session.conversation.condense)
    await conn.send(HistoryCompacted())


async def _handle_interrupt(conn: _Connection, message: Interrupt) -> None:
    """Queued by the agent-server and read at the agent's next step. A message for a
    turn that just ended would be lost: the client's own fallback sends it as a turn."""
    if conn.turn_id != message.turn_id or conn.session is None:
        return
    conversation = cast(Any, conn.session.conversation)  # same SDK typing quirk as `send()`
    await asyncio.to_thread(conversation.send_message, message.text)


async def _handle_confirm_action(conn: _Connection, message: ConfirmAction) -> None:
    session = conn.session
    assert session is not None
    if message.accept:
        # No public SDK method for the "accept" case -- POST the same endpoint
        # the SDK itself uses (see module docstring).
        await asyncio.to_thread(
            session.workspace.client.post,
            f"/api/conversations/{session.conversation.id}/events/respond_to_confirmation",
            json={"accept": True, "reason": "User approved"},
        )
    else:
        await asyncio.to_thread(session.conversation.reject_pending_actions)


def _keep_change(path: str) -> bool:
    return not path.startswith(_INTERNAL_PREFIXES) and path not in _INTERNAL_NAMES


def _cap(changes: list[GitChangeDTO]) -> list[GitChangeDTO]:
    return [] if len(changes) > _MAX_REPORTED_CHANGES else changes


def _map_changes(raw_changes: list[GitChange]) -> list[GitChangeDTO]:
    return _cap(
        [
            GitChangeDTO(status=c.status.value, path=str(c.path))
            for c in raw_changes
            if _keep_change(str(c.path))
        ]
    )


async def _current_changes(session: AgentSession) -> list[GitChangeDTO]:
    """The agent's real changes to the project. Prefers the WP08d working
    copy's diff against the **session baseline** -- `workspace.git_changes`
    compares against the source repo's HEAD instead, so it also lists files
    that were merely untracked or ignored in /workspace/source at session start
    (`.claude/…`, stray `*.bak`, …) as if the agent had added them."""
    working_copy = session.working_copy
    if working_copy is not None and working_copy.is_git:
        pairs = await asyncio.to_thread(working_copy.changed_files)
        return _cap([GitChangeDTO(status=s, path=p) for s, p in pairs if _keep_change(p)])
    raw = await asyncio.to_thread(session.workspace.git_changes, ".")
    return _map_changes(list(raw))


async def _emit_files_changed(conn: _Connection) -> list[GitChangeDTO]:
    session = conn.session
    assert session is not None
    changes = await _current_changes(session)
    await conn.send(FilesChanged(changes=changes))
    return changes


async def _emit_post_turn(conn: _Connection) -> None:
    session = conn.session
    assert session is not None
    await _emit_files_changed(conn)

    metrics = session.conversation.conversation_stats.get_combined_metrics()
    accumulated = metrics.accumulated_token_usage
    # `context_stats` is the gauge -- "how full is the window right now" -- so it
    # needs the LAST call's prompt size against the model's real window, NOT the
    # lifetime sum in `accumulated_token_usage` (that only ever grows and is
    # meaningless as an occupancy). `usage` keeps the lifetime totals for the
    # cost / tokens-spent display. llama.cpp reports no window, so use the config.
    window = session.context_window
    last_call = metrics.token_usages[-1] if metrics.token_usages else None
    current_prompt = last_call.prompt_tokens if last_call else 0
    recent = list(session.conversation.state.events)[-8:]
    condensed = any(type(e).__name__.startswith("Condensation") for e in recent)
    await conn.send(
        ContextStats(prompt_tokens=current_prompt, context_window=window, compacted=condensed)
    )
    await conn.send(
        Usage(
            accumulated_cost=metrics.accumulated_cost,
            prompt_tokens=accumulated.prompt_tokens if accumulated else 0,
            completion_tokens=accumulated.completion_tokens if accumulated else 0,
            context_window=window,
        )
    )


def _no_working_copy() -> ErrorMessage:
    return ErrorMessage(
        code="NO_WORKING_COPY",
        message="This session has no project working copy (no project_path was given).",
    )


async def _handle_request_diff(conn: _Connection, message: RequestDiff) -> None:
    session = conn.session
    assert session is not None
    if session.working_copy is None:
        await conn.send(_no_working_copy())
        return
    try:
        raw = await asyncio.to_thread(session.working_copy.file_diff, message.path)
    except AppError as exc:
        await conn.send(_error_from(exc))
        return
    unified, was_truncated = truncate(raw)
    await conn.send(FileDiffMessage(path=message.path, unified=unified, truncated=was_truncated))


async def _handle_request_bundle_diff(conn: _Connection) -> None:
    session = conn.session
    assert session is not None
    if session.working_copy is None:
        await conn.send(_no_working_copy())
        return
    try:
        raw = await asyncio.to_thread(session.working_copy.bundle_diff)
    except AppError as exc:
        await conn.send(_error_from(exc))
        return
    unified, was_truncated = truncate(raw)
    await conn.send(BundleDiffMessage(unified=unified, truncated=was_truncated))


async def _handle_restore_checkpoint(conn: _Connection, message: RestoreCheckpoint) -> None:
    session = conn.session
    assert session is not None
    if session.working_copy is None:
        await conn.send(_no_working_copy())
        return
    try:
        await asyncio.to_thread(session.working_copy.restore, message.checkpoint_id)
    except AppError as exc:
        await conn.send(_error_from(exc))
        return
    await conn.send(CheckpointRestored(checkpoint_id=message.checkpoint_id))
    if _auto_applies(session):
        await _sync_to_host(conn, session)
    await _emit_files_changed(conn)


def _capabilities() -> list[str]:
    config = load_openhands_config()
    extra = {
        "deltas": config.llm.stream,
        "resume": config.sandbox.persistent_conversations,
    }
    return [*CAPABILITIES, *(name for name, offered in extra.items() if offered)]


async def _pull_from_host(conn: _Connection, session: AgentSession) -> list[str]:
    """What the user edited since the last sync goes into the copy before the agent
    starts, so it works on the current file rather than end in a conflict (WP17 §5).
    Protected paths stay out: secrets are masked from the sandbox on purpose."""
    project_path = session.project_path
    working_copy = session.working_copy
    assert project_path is not None and working_copy is not None

    current = await asyncio.to_thread(_snapshot_host_tree, project_path)
    known = conn.baseline_hashes
    edited = [p for p, h in current.items() if known.get(p) != h and not apply_mod.is_protected(p)]
    removed = [p for p in known if p not in current and not apply_mod.is_protected(p)]
    # Files the agent left pending are not the user's: the sync owns them.
    edited = [p for p in edited if p not in conn.conflicts]
    if not edited and not removed:
        return []

    for relpath in edited:
        await asyncio.to_thread(working_copy.write_file, relpath, project_path / relpath)
        conn.baseline_hashes[relpath] = current[relpath]
    for relpath in removed:
        await asyncio.to_thread(working_copy.remove_file, relpath)
        conn.baseline_hashes.pop(relpath, None)
    if not conn.conflicts:
        await asyncio.to_thread(working_copy.mark_applied)
    return sorted([*edited, *removed])


def _auto_applies(session: AgentSession) -> bool:
    working_copy = session.working_copy
    return not session.read_only and working_copy is not None and working_copy.is_git


async def _sync_to_host(
    conn: _Connection,
    session: AgentSession,
    *,
    only_paths: set[str] | None = None,
    force: bool = False,
) -> None:
    """Writes what the real repo has not received yet. `refs/agenticenv/applied`
    only moves once nothing is left in conflict, so a skipped file stays pending
    until it is overwritten or the next sync goes through."""
    working_copy = session.working_copy
    project_path = session.project_path
    assert working_copy is not None and project_path is not None

    pairs = await asyncio.to_thread(working_copy.changed_since_applied)
    changes = [GitChangeDTO(status=s, path=p) for s, p in pairs if _keep_change(p)]
    result, new_hashes = await asyncio.to_thread(
        apply_mod.apply_changes,
        changes=changes,
        host_root=project_path,
        read_sandbox=working_copy.read_file,
        is_executable=working_copy.is_executable,
        baseline_hashes=conn.baseline_hashes,
        only_paths=only_paths,
        force=force,
    )
    conn.baseline_hashes = new_hashes

    # A protected file will never be written: waiting on it would hold everything back.
    skipped = {p for p, r in result.skipped if r != apply_mod.PROTECTED_REASON}
    if only_paths is None:
        conn.conflicts = skipped
    else:
        conn.conflicts = (conn.conflicts - {p for p, _ in result.applied}) | skipped
    if not conn.conflicts:
        await asyncio.to_thread(working_copy.mark_applied)

    if result.applied or result.skipped:
        await conn.send(
            ChangesApplied(
                applied=[AppliedEntry(path=p, status=s) for p, s in result.applied],
                skipped=[SkippedEntry(path=p, reason=r) for p, r in result.skipped],
            )
        )


async def _handle_apply_changes(conn: _Connection, message: ApplyChanges) -> None:
    session = conn.session
    assert session is not None
    if session.read_only:
        await conn.send(
            ErrorMessage(
                code="READ_ONLY_SESSION",
                message="This session is read-only (Ask / Plan mode); apply_changes is disabled.",
            )
        )
        return
    if session.working_copy is None or session.project_path is None:
        await conn.send(_no_working_copy())
        return

    only_paths = set(message.paths) if message.paths is not None else None
    await _sync_to_host(conn, session, only_paths=only_paths, force=message.force)
    await _emit_files_changed(conn)


async def _run_server() -> None:
    host = os.environ.get("AGX_OPENHANDS_BRIDGE_HOST", _DEFAULT_HOST)
    port = int(os.environ.get("AGX_OPENHANDS_BRIDGE_PORT", _DEFAULT_PORT))
    # A fresh bridge owns no session, so every agent-server-* container is a
    # leftover from a previous run -- stop them before accepting connections.
    reaped = await asyncio.to_thread(reap_orphan_sandboxes, None)
    if reaped:
        logger.info("reaped orphan sandbox containers at startup", extra={"containers": reaped})
    logger.info("openhands-bridge listening", extra={"host": host, "port": port})
    # Short keepalive: when the VS Code extension host restarts, its socket may
    # linger half-open -- a tight ping keeps a stale connection (and, with it,
    # ownership of the active session) from blocking a fresh one for long.
    async with serve(
        _handle_connection,
        host,
        port,
        ping_interval=10,
        ping_timeout=8,
        **serve_options(ensure_token()),
    ):
        await asyncio.Future()  # run forever


def main() -> None:
    asyncio.run(_run_server())


if __name__ == "__main__":
    main()
