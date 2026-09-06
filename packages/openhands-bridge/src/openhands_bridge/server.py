"""WebSocket server: one bridge process, at most one `AgentSession` at a time.

Connections themselves are never gated -- a client may connect, list MCP
servers, and read health at any time, and reconnect freely. Only creating a
second concurrent `AgentSession` (a second Docker sandbox) is refused, with a
`SESSION_BUSY` error, without closing the connection.


Owns the full lifecycle of a chat session on behalf of an external client (the
`agenticenv-chat` VS Code extension): starts the Docker sandbox via
`openhands_adapter.AgentSession`, streams every SDK `Event` out over the socket
as it happens, and after each turn pushes the modified-files list and the
context/cost usage -- all backed by SDK APIs that already exist (see
blueprint/wp/WP08b-openhands-sandbox.md, section on the VS Code chat client).

Concurrency: `AgentSession.send(..., blocking=True)` runs in a worker thread
(`asyncio.to_thread`) so it never blocks the event loop; the SDK's own
callback -- fired from ITS OWN internal websocket-listener thread, not from
that worker thread and not from our event loop -- hands events back to the
loop via `asyncio.run_coroutine_threadsafe`. A confirmation pause is detected
from a `ConversationStateUpdateEvent(key="execution_status",
value="waiting_for_confirmation")`, matching how `RemoteState` itself tracks
status (`remote_conversation.py: create_state_update_callback`); resolving it
is a direct POST to the same `respond_to_confirmation` endpoint
`AgentSession._ensure_llm` already uses for `switch_llm` -- there is no public
SDK method for the "accept" case, only for "reject" (`reject_pending_actions`).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading

from corelib.errors import AppError
from corelib.logging import get_logger
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from openhands_adapter import (
    AgentSession,
    ConfirmRisky,
    ConversationStateUpdateEvent,
    Event,
    load_openhands_config,
)
from openhands_bridge.mcp_catalog import list_mcp_servers
from openhands_bridge.protocol import (
    AwaitingConfirmation,
    ConfirmAction,
    ErrorMessage,
    EventMessage,
    FilesChanged,
    GitChangeDTO,
    ListMcpServers,
    McpServerEntry,
    McpServers,
    OutboundMessage,
    SessionStarted,
    StartSession,
    Usage,
    UserMessage,
    parse_inbound,
    serialize_outbound,
)

logger = get_logger(__name__)

_DEFAULT_PORT = 8300
_DEFAULT_HOST = "127.0.0.1"

# At most one *AgentSession* (= one Docker sandbox) at a time across the whole
# process, but connections are NOT gated: a client may connect, list MCP
# servers, and see health at any time, and reconnect freely (VS Code reloads
# its extension host, which drops and reopens the socket). `_session_owner` is
# the connection object that currently owns the active session; the guard is
# held only briefly around create/teardown, never for a connection's lifetime
# (that earlier design made a reconnecting client flap on SESSION_BUSY).
_session_guard = asyncio.Lock()
_session_owner: ServerConnection | None = None


async def _send(ws: ServerConnection, message: OutboundMessage) -> None:
    with contextlib.suppress(ConnectionClosed):
        await ws.send(serialize_outbound(message))


def _error_from(exc: AppError) -> ErrorMessage:
    return ErrorMessage(code=exc.code, message=exc.message, details=dict(exc.details))


async def _handle_connection(ws: ServerConnection) -> None:
    await _serve_one_connection(ws)


class _EventRelay:
    """Forwards `Event` callbacks to the client, buffering anything fired
    before the client has been sent `session_started`.

    `AgentSession.__enter__` starts the SDK's own WebSocket listener thread as
    part of creating the conversation, and that thread can fire callbacks
    (e.g. the initial state snapshot) *before* `_start_session` gets a chance
    to send `session_started` -- observed for real in `test_bridge_e2e.py`
    (an `event` message arriving as the very first message). Buffering here,
    then flushing right after `session_started` is sent, keeps the ordering
    guarantee simple for the client instead of pushing "events may arrive
    before session_started" onto every client implementation.
    """

    def __init__(self, ws: ServerConnection, loop: asyncio.AbstractEventLoop) -> None:
        self._ws = ws
        self._loop = loop
        self._lock = threading.Lock()
        self._buffering = True
        self._buffer: list[Event] = []
        self.session: AgentSession | None = None

    def on_event(self, event: Event) -> None:
        with self._lock:
            if self._buffering:
                self._buffer.append(event)
                return
        self._dispatch(event)

    def _dispatch(self, event: Event) -> None:
        asyncio.run_coroutine_threadsafe(
            _send(self._ws, EventMessage(event=event.model_dump(mode="json"))), self._loop
        )
        if (
            isinstance(event, ConversationStateUpdateEvent)
            and event.key == "execution_status"
            and event.value == "waiting_for_confirmation"
            and self.session is not None
        ):
            asyncio.run_coroutine_threadsafe(
                _send(
                    self._ws,
                    AwaitingConfirmation(conversation_id=str(self.session.conversation.id)),
                ),
                self._loop,
            )

    async def release(self, session: AgentSession) -> None:
        """Call once `session_started` has actually been sent."""
        self.session = session
        with self._lock:
            buffered, self._buffer = self._buffer, []
            self._buffering = False
        for event in buffered:
            self._dispatch(event)


async def _serve_one_connection(ws: ServerConnection) -> None:
    global _session_owner
    loop = asyncio.get_running_loop()
    relay = _EventRelay(ws, loop)
    session: AgentSession | None = None

    try:
        async for raw in ws:
            try:
                inbound = parse_inbound(raw)
            except AppError as exc:
                await _send(ws, _error_from(exc))
                continue

            if isinstance(inbound, StartSession):
                if session is not None:
                    await _send(
                        ws,
                        ErrorMessage(
                            code="ALREADY_STARTED",
                            message="This connection already has an active session.",
                        ),
                    )
                    continue
                async with _session_guard:
                    if _session_owner is not None:
                        await _send(
                            ws,
                            ErrorMessage(
                                code="SESSION_BUSY",
                                message="A chat session is already active on this bridge.",
                            ),
                        )
                        continue
                    _session_owner = ws
                session = await _start_session(ws, relay, inbound)
                if session is None:
                    async with _session_guard:
                        _session_owner = None

            elif isinstance(inbound, UserMessage):
                if session is None:
                    await _send(
                        ws, ErrorMessage(code="NO_SESSION", message="Send start_session first.")
                    )
                    continue
                await _handle_user_message(ws, session, inbound)

            elif isinstance(inbound, ConfirmAction):
                if session is None:
                    await _send(ws, ErrorMessage(code="NO_SESSION", message="No active session."))
                    continue
                await _handle_confirm_action(session, inbound)

            elif isinstance(inbound, ListMcpServers):
                servers = await asyncio.to_thread(list_mcp_servers)
                await _send(
                    ws,
                    McpServers(
                        servers=[
                            McpServerEntry(
                                name=s.name,
                                transport=s.transport,
                                tools_allowlist=s.tools_allowlist,
                            )
                            for s in servers
                        ]
                    ),
                )
    finally:
        if session is not None:
            await asyncio.to_thread(session.__exit__, None, None, None)
        async with _session_guard:
            if _session_owner is ws:
                _session_owner = None


async def _start_session(
    ws: ServerConnection, relay: _EventRelay, request: StartSession
) -> AgentSession | None:
    session = AgentSession(
        oh_config=load_openhands_config(),
        confirmation_policy=ConfirmRisky(),
        callbacks=[relay.on_event],
        project_path=request.project_path,
    )
    try:
        await asyncio.to_thread(session.__enter__)
    except AppError as exc:
        await _send(ws, _error_from(exc))
        return None

    await _send(
        ws,
        SessionStarted(conversation_id=str(session.conversation.id), llm_source=session.llm_source),
    )
    if session.project_writable is False and request.project_path:
        await _send(
            ws,
            ErrorMessage(
                code="PROJECT_READONLY",
                message=(
                    "The sandbox (uid 10001) can't write your project folder, so the agent "
                    "can read the code but not edit it. Grant access once, keeping your "
                    "ownership:\n"
                    f"  setfacl -R -m u:10001:rwX -m d:u:10001:rwX -m d:u:$(id -u):rwX "
                    f"{request.project_path}\n"
                    "(or, without ACLs:  chmod -R o+rwX <folder>)"
                ),
            ),
        )
    await relay.release(session)
    return session


# Agent-server internals that live under the sandbox workspace and must never be
# shown as "the agent changed this file in your project".
_INTERNAL_PREFIXES = ("conversations/", ".git/", ".openhands/")
_INTERNAL_NAMES = {"owner_lease.json", "meta.json"}
# If `git_changes` returns more than this, the working dir almost certainly is
# not a git repo and the agent-server listed every file -- send nothing rather
# than a wall of noise.
_MAX_REPORTED_CHANGES = 200


async def _handle_user_message(
    ws: ServerConnection, session: AgentSession, message: UserMessage
) -> None:
    try:
        await asyncio.to_thread(session.send, message.text, blocking=True)
    except AppError as exc:
        await _send(ws, _error_from(exc))
        return

    raw_changes = await asyncio.to_thread(session.workspace.git_changes, ".")
    changes = [
        GitChangeDTO(status=c.status.value, path=str(c.path))
        for c in raw_changes
        if not str(c.path).startswith(_INTERNAL_PREFIXES) and str(c.path) not in _INTERNAL_NAMES
    ]
    if len(changes) > _MAX_REPORTED_CHANGES:
        changes = []
    await _send(ws, FilesChanged(changes=changes))

    metrics = session.conversation.conversation_stats.get_combined_metrics()
    token_usage = metrics.accumulated_token_usage
    await _send(
        ws,
        Usage(
            accumulated_cost=metrics.accumulated_cost,
            prompt_tokens=token_usage.prompt_tokens if token_usage else 0,
            completion_tokens=token_usage.completion_tokens if token_usage else 0,
            context_window=token_usage.context_window if token_usage else 0,
        ),
    )


async def _handle_confirm_action(session: AgentSession, message: ConfirmAction) -> None:
    if message.accept:
        await asyncio.to_thread(
            session.workspace.client.post,
            f"/api/conversations/{session.conversation.id}/events/respond_to_confirmation",
            json={"accept": True, "reason": "User approved"},
        )
    else:
        await asyncio.to_thread(session.conversation.reject_pending_actions)


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
