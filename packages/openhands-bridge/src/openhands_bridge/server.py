"""WebSocket server: one bridge process, at most one `AgentSession` at a time.

Protocol v2 (agenticenv-chat/docs/bridge-v2-spec.md) + WP08d (the disposable
sandbox working copy). Every connection opens with `hello`/`welcome`
capability negotiation; every outbound message carries a monotonic `seq`;
each user message is wrapped in `turn_started`/`turn_finished`, can be
cancelled mid-flight, and -- when the session has a project working copy --
is preceded by a `checkpoint` the client can restore. `apply_changes` writes
the agent's edits from the throwaway copy back into the real host repo,
performed by *this* process (which runs as the user, unlike the uid-10001
agent-server).

Connections themselves are never gated -- a client may connect, negotiate,
list MCP servers, and reconnect freely (VS Code restarts its extension host,
dropping and reopening the socket). Only creating a second concurrent
`AgentSession` (a second Docker sandbox) is refused, with `SESSION_BUSY`,
without closing the connection.

Concurrency: the run is triggered non-blocking (`session.send(blocking=False)`
in a worker thread) and the turn's terminal status is awaited on the event
loop -- watching the SDK's own `ConversationStateUpdateEvent` callbacks (fired
from the SDK's internal websocket-listener thread) with a REST poll as a
fallback. This keeps `cancel_turn` responsive: it rejects any pending action
and calls `conversation.pause()`, moving the run to a terminal/`paused` state
the same watcher observes and reports as a cancelled turn.

The confirmation policy is `NeverConfirm` (WP08d): the agent works on a
disposable copy and nothing reaches the real repo without an explicit
`apply_changes`, so the copy is the safety boundary. `waiting_for_confirmation`
should not occur; if it ever does, the turn watcher still bounds the wait by
`run_timeout_s` rather than hanging.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from corelib.errors import AppError
from corelib.logging import get_logger
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from openhands_adapter import (
    AgentSession,
    ConversationStateUpdateEvent,
    Event,
    GitChange,
    NeverConfirm,
    load_openhands_config,
)
from openhands_bridge import apply as apply_mod
from openhands_bridge.mcp_catalog import list_mcp_servers
from openhands_bridge.protocol import (
    AppliedEntry,
    ApplyChanges,
    AwaitingConfirmation,
    BundleDiffMessage,
    CancelTurn,
    ChangesApplied,
    CheckpointMessage,
    CheckpointRestored,
    ConfirmAction,
    ContextStats,
    DiscardChanges,
    ErrorMessage,
    EventMessage,
    FileDiffMessage,
    FilesChanged,
    GitChangeDTO,
    Hello,
    InboundMessage,
    ListMcpServers,
    McpServerEntry,
    McpServers,
    OutboundMessage,
    RequestBundleDiff,
    RequestDiff,
    RestoreCheckpoint,
    SessionStarted,
    SkippedEntry,
    StartSession,
    TurnFinished,
    TurnFinishedReason,
    TurnStarted,
    Usage,
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

# Agent-server internals that live under the sandbox workspace and must never be
# shown as "the agent changed this file in your project".
_INTERNAL_PREFIXES = ("conversations/", ".git/", ".openhands/")
_INTERNAL_NAMES = {"owner_lease.json", "meta.json"}
# If `git_changes` returns more than this, the working dir almost certainly is
# not a git repo and the agent-server listed every file -- send nothing rather
# than a wall of noise.
_MAX_REPORTED_CHANGES = 200

# At most one *AgentSession* (= one Docker sandbox) at a time across the whole
# process, but connections are NOT gated. `_session_owner` is the connection
# that currently owns the active session; the guard is held only briefly
# around create/teardown, never for a connection's lifetime.
_session_guard = asyncio.Lock()
_session_owner: _Connection | None = None


def _error_from(exc: AppError) -> ErrorMessage:
    return ErrorMessage(code=exc.code, message=exc.message, details=dict(exc.details))


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


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
        self._conn.send_threadsafe(EventMessage(event=event.model_dump(mode="json")))
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
        self.baseline_hashes: dict[str, str] = {}
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
            with contextlib.suppress(ConnectionClosed):
                await self.ws.send(serialize_outbound(message))

    def send_threadsafe(self, message: OutboundMessage) -> None:
        asyncio.run_coroutine_threadsafe(self.send(message), self.loop)

    def note_status_threadsafe(self, value: str) -> None:
        def _apply() -> None:
            self._last_status = value
            if value in _TERMINAL_TURN_STATUSES:
                self._turn_terminal.set()

        self.loop.call_soon_threadsafe(_apply)


async def _handle_connection(ws: ServerConnection) -> None:
    global _session_owner
    loop = asyncio.get_running_loop()
    conn = _Connection(ws, loop)
    try:
        async for raw in ws:
            try:
                inbound = parse_inbound(raw)
            except AppError as exc:
                await conn.send(_error_from(exc))
                continue
            await _dispatch_inbound(conn, inbound)
    finally:
        if conn.session is not None:
            await asyncio.to_thread(conn.session.__exit__, None, None, None)
        async with _session_guard:
            if _session_owner is conn:
                _session_owner = None


async def _dispatch_inbound(conn: _Connection, inbound: InboundMessage) -> None:
    global _session_owner

    if isinstance(inbound, Hello):
        conn.client_id = inbound.client
        conn.protocol = inbound.protocol
        await conn.send(Welcome())
        return

    if isinstance(inbound, ListMcpServers):
        servers = await asyncio.to_thread(list_mcp_servers)
        await conn.send(
            McpServers(
                servers=[
                    McpServerEntry(
                        name=s.name, transport=s.transport, tools_allowlist=s.tools_allowlist
                    )
                    for s in servers
                ]
            )
        )
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

    if isinstance(inbound, UserMessage):
        await _handle_user_message(conn, inbound)
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
    elif isinstance(inbound, DiscardChanges):
        await _handle_discard_changes(conn, inbound)


async def _start_session(conn: _Connection, request: StartSession) -> bool:
    # NeverConfirm: under WP08d the agent works on a disposable copy and nothing
    # reaches the real repo without an explicit `apply_changes`, so the copy is
    # the safety boundary -- a per-action confirmation pause only wedges the turn
    # (`ConfirmRisky` also adds a security-analysis LLM call per action).
    session = AgentSession(
        oh_config=load_openhands_config(),
        confirmation_policy=NeverConfirm(),
        callbacks=[conn.relay.on_event],
        project_path=request.project_path,
        read_only=request.mode == "read_only",
    )
    try:
        await asyncio.to_thread(session.__enter__)
    except AppError as exc:
        await conn.send(_error_from(exc))
        return False

    conn.session = session
    await conn.send(
        SessionStarted(
            conversation_id=str(session.conversation.id),
            llm_source=session.llm_source,
            mode="read_only" if session.read_only else "agent",
        )
    )
    await conn.relay.release(session)

    if session.project_path is not None:
        conn.baseline_hashes = await asyncio.to_thread(_snapshot_host_tree, session.project_path)
    return True


def _snapshot_host_tree(root: Path) -> dict[str, str]:
    """Content hashes of the real repo's tracked files at session start --
    `apply_changes` compares against these to refuse a blind overwrite of a
    file the user edited meanwhile (WP08d conflict rule)."""
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
    no client answering it, the turn must still end rather than hang forever."""
    deadline = conn.loop.time() + session.run_timeout_s
    while True:
        try:
            await asyncio.wait_for(conn._turn_terminal.wait(), timeout=5.0)
            return conn._last_status
        except TimeoutError:
            status = _poll_status(session)
            if status in _TERMINAL_TURN_STATUSES:
                return status or "error"
            if conn.loop.time() > deadline:
                if status == "waiting_for_confirmation":
                    with contextlib.suppress(Exception):
                        await asyncio.to_thread(session.conversation.reject_pending_actions)
                return "timeout"


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
    conn._turn_terminal.clear()

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

    reason: TurnFinishedReason = "completed"
    try:
        await asyncio.to_thread(_fire_run, session, _compose_prompt(message))
    except AppError as exc:
        await conn.send(_error_from(exc))
        reason = "error"
    else:
        reason = _reason_for(conn, await _await_turn_terminal(conn, session))

    await _emit_post_turn(conn)
    await conn.send(TurnFinished(turn_id=turn_id, reason=reason))
    conn.turn_id = None


async def _handle_cancel(conn: _Connection, message: CancelTurn) -> None:
    if conn.turn_id != message.turn_id or conn.session is None:
        return
    conn.cancelled = True
    conversation = conn.session.conversation
    # `pause()` unwinds a running loop; `reject_pending_actions()` unblocks a
    # turn parked at `waiting_for_confirmation` (where `pause()` is a no-op).
    # Do both -- whichever applies produces a terminal/paused status the turn
    # watcher is waiting on, so "stopping" always resolves.
    with contextlib.suppress(Exception):
        await asyncio.to_thread(conversation.reject_pending_actions)
    with contextlib.suppress(Exception):
        await asyncio.to_thread(conversation.pause)


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


def _map_changes(raw_changes: list[GitChange]) -> list[GitChangeDTO]:
    changes = [
        GitChangeDTO(status=c.status.value, path=str(c.path))
        for c in raw_changes
        if not str(c.path).startswith(_INTERNAL_PREFIXES) and str(c.path) not in _INTERNAL_NAMES
    ]
    if len(changes) > _MAX_REPORTED_CHANGES:
        return []
    return changes


async def _emit_files_changed(conn: _Connection) -> list[GitChangeDTO]:
    session = conn.session
    assert session is not None
    raw = await asyncio.to_thread(session.workspace.git_changes, ".")
    changes = _map_changes(list(raw))
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
    await _emit_files_changed(conn)


async def _handle_discard_changes(conn: _Connection, message: DiscardChanges) -> None:
    session = conn.session
    assert session is not None
    if session.working_copy is None:
        await conn.send(_no_working_copy())
        return
    try:
        await asyncio.to_thread(session.working_copy.discard, message.paths)
    except AppError as exc:
        await conn.send(_error_from(exc))
        return
    await _emit_files_changed(conn)


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

    raw_changes = await asyncio.to_thread(session.workspace.git_changes, ".")
    changes = _map_changes(list(raw_changes))
    only_paths = set(message.paths) if message.paths is not None else None

    result, new_hashes = await asyncio.to_thread(
        apply_mod.apply_changes,
        changes=changes,
        host_root=session.project_path,
        read_sandbox=session.working_copy.read_file,
        baseline_hashes=conn.baseline_hashes,
        only_paths=only_paths,
        force=message.force,
    )
    conn.baseline_hashes = new_hashes
    await conn.send(
        ChangesApplied(
            applied=[AppliedEntry(path=p, status=s) for p, s in result.applied],
            skipped=[SkippedEntry(path=p, reason=r) for p, r in result.skipped],
        )
    )
    await _emit_files_changed(conn)


async def _run_server() -> None:
    host = os.environ.get("AGX_OPENHANDS_BRIDGE_HOST", _DEFAULT_HOST)
    port = int(os.environ.get("AGX_OPENHANDS_BRIDGE_PORT", _DEFAULT_PORT))
    logger.info("openhands-bridge listening", extra={"host": host, "port": port})
    # Short keepalive: when the VS Code extension host restarts, its socket may
    # linger half-open -- a tight ping keeps a stale connection (and, with it,
    # ownership of the active session) from blocking a fresh one for long.
    async with serve(_handle_connection, host, port, ping_interval=10, ping_timeout=8):
        await asyncio.Future()  # run forever


def main() -> None:
    asyncio.run(_run_server())


if __name__ == "__main__":
    main()
