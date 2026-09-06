"""Drives an OpenHands agent-server sandbox against the local llama-server.

Replaces the manual flow validated by hand (create conversation -> `switch_llm`
-> post event -> run -> read the event log) with a small, typed API on top of
the OpenHands SDK. See blueprint/wp/WP08b-openhands-sandbox.md.

Flow, matching the SDK's own behaviour (not re-implemented REST calls):

1. The `Agent` sent at conversation-creation time already carries the local
   LLM config (`agent.llm`), and the agent-server honours it -- no
   `switch_llm` call is needed on a compatible image (verified: 1.21.0-python
   ~ openhands-sdk 1.21.0, see the pyproject.toml pin comment).
2. `_ensure_llm` re-reads the conversation from the server after creation and
   only falls back to an explicit `POST .../switch_llm` if the persisted agent
   does not actually match what we asked for -- so the fallback is verified,
   not blind.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, cast

from corelib.config import get_settings
from corelib.errors import DependencyError
from corelib.logging import get_logger
from openhands.sdk import LLM, Agent, Conversation, Event, Tool
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.sdk.conversation.exceptions import ConversationRunError
from openhands.sdk.conversation.impl.remote_conversation import RemoteConversation
from openhands.sdk.conversation.response_utils import get_agent_final_response
from openhands.sdk.security.confirmation_policy import ConfirmationPolicyBase, NeverConfirm
from openhands.sdk.utils.command import execute_command
from openhands.tools.preset.default import register_default_tools
from pydantic import SecretStr

from openhands_adapter.config import OpenHandsConfig, load_openhands_config
from openhands_adapter.docker_workspace import AgenticEnvDockerWorkspace
from openhands_adapter.working_copy import WorkingCopy

logger = get_logger(__name__)

_DEFAULT_TOOLS = (
    # Registered by register_default_tools() under these exact snake_case keys
    # (openhands.sdk.tool.registry) -- NOT the "TerminalTool"-style class names.
    Tool(name="terminal"),
    Tool(name="file_editor"),
    Tool(name="task_tracker"),
)

# WP08d: the host project is bind-mounted READ-ONLY here; the agent works on a
# disposable `cp -a` copy at _WORKING_COPY (a subdir of /workspace, so the
# agent-server's own /workspace/conversations stays out of the copy).
_PROJECT_SOURCE = "/workspace/source"
_WORKING_COPY = "/workspace/project"

# Idempotent: `register_default_tools` just re-imports/re-registers on repeat calls.
_tools_registered = False


def _ensure_tools_registered() -> None:
    global _tools_registered
    if not _tools_registered:
        register_default_tools(enable_browser=False)
        _tools_registered = True


@dataclass(frozen=True)
class AgentResult:
    """Outcome of one `AgentSession.send()` call."""

    conversation_id: str
    final_text: str
    execution_status: str
    # "create_payload": the agent-server used the LLM sent at conversation
    # creation, as-is. "switch_llm": that didn't hold, and the adapter had to
    # fall back to POST /switch_llm to correct it -- see module docstring.
    llm_source: str


def _check_image_present(image: str) -> None:
    proc = execute_command(["docker", "image", "inspect", image])
    if proc.returncode != 0:
        raise DependencyError(
            f"agent-server image not present locally: {image}",
            details={"image": image, "fix": f"docker pull {image}"},
        )


def _build_agent(cfg: OpenHandsConfig, mcp_config: dict[str, object] | None) -> tuple[Agent, str]:
    served_model = get_settings().llm.served_model
    model = f"openai/{served_model}"
    ctx_size = get_settings().llm.ctx_size
    timeout_s = get_settings().llm.request_timeout_s

    def _llm(usage_id: str) -> LLM:
        return LLM(
            usage_id=usage_id,
            model=model,
            base_url=cfg.llm.sandbox_base_url,
            api_key=SecretStr("local-llm"),  # llama-server does not enforce a real key
            temperature=0.0,
            timeout=timeout_s,
        )

    # Without a condenser OpenHands never trims history: it grows every step
    # until llama-server rejects the request ("context window exceeded") and the
    # turn dies. The summarizing condenser folds the oldest events into a summary
    # once the view approaches the model's window, keeping the working context
    # bounded. Trigger at ~70% of ctx_size so a turn always has room to finish.
    condenser = LLMSummarizingCondenser(
        llm=_llm("condenser"),
        max_tokens=int(ctx_size * 0.7),
        max_size=120,
        keep_first=4,
    )
    agent = Agent(
        llm=_llm("agent"),
        tools=list(_DEFAULT_TOOLS),
        mcp_config=mcp_config or {},
        condenser=condenser,
    )
    return agent, model


def _ensure_llm(
    conversation: RemoteConversation, agent: Agent, expected_model: str, expected_base_url: str
) -> str:
    """Verifies the server actually picked up `agent.llm`; falls back to `switch_llm`."""
    info = conversation.state.refresh_from_server()
    persisted_llm = (info.get("agent") or {}).get("llm") or {}
    if (
        persisted_llm.get("model") == expected_model
        and persisted_llm.get("base_url") == expected_base_url
    ):
        return "create_payload"

    logger.info(
        "agent-server did not honor the LLM sent at conversation creation; "
        "falling back to switch_llm",
        extra={"conversation_id": str(conversation.id)},
    )
    resp = conversation.workspace.client.post(
        f"/api/conversations/{conversation.id}/switch_llm",
        json={"llm": agent.llm.model_dump(mode="json", context={"expose_secrets": True})},
    )
    if resp.status_code == 404:
        raise DependencyError(
            "agent-server image does not expose /switch_llm; incompatible with this adapter",
            details={"conversation_id": str(conversation.id)},
        )
    resp.raise_for_status()
    return "switch_llm"


class AgentSession:
    """Owns one Docker agent-server sandbox and one `RemoteConversation`.

    Usage::

        with AgentSession() as session:
            result = session.send("...")
    """

    def __init__(
        self,
        *,
        oh_config: OpenHandsConfig | None = None,
        confirmation_policy: ConfirmationPolicyBase | None = None,
        mcp_config: dict[str, object] | None = None,
        callbacks: list[Callable[[Event], None]] | None = None,
        project_path: str | Path | None = None,
        read_only: bool = False,
    ) -> None:
        self._cfg = oh_config or load_openhands_config()
        self._confirmation_policy = confirmation_policy or NeverConfirm()
        self._mcp_config = mcp_config
        self._callbacks = callbacks or []
        # Host directory bind-mounted read-only; the agent works on a copy.
        # None -> the agent works in an empty in-container /workspace.
        self._project_path = Path(project_path).expanduser().resolve() if project_path else None
        self._read_only = read_only
        self._working_copy: WorkingCopy | None = None
        self._workspace: AgenticEnvDockerWorkspace | None = None
        self._conversation: RemoteConversation | None = None
        self._llm_source = "create_payload"

    @property
    def conversation(self) -> RemoteConversation:
        """The live conversation. Raises outside of a `with` block.

        Exposed for callers (e.g. packages/openhands-bridge) that need direct
        access to SDK-native state -- `conversation.state.events`,
        `conversation.conversation_stats` -- beyond what `send()` returns.
        """
        if self._conversation is None:
            raise DependencyError("AgentSession used outside of a `with` block")
        return self._conversation

    @property
    def workspace(self) -> AgenticEnvDockerWorkspace:
        """The live sandbox workspace. Raises outside of a `with` block.

        Exposed for callers that need `workspace.git_changes(...)`/`.git_diff(...)`.
        """
        if self._workspace is None:
            raise DependencyError("AgentSession used outside of a `with` block")
        return self._workspace

    @property
    def llm_source(self) -> str:
        """`"create_payload"` or `"switch_llm"` -- see `_ensure_llm`. `"create_payload"`
        (the default) until `__enter__` has actually run."""
        return self._llm_source

    @property
    def project_path(self) -> Path | None:
        """The host directory bound read-only into the sandbox, or None."""
        return self._project_path

    @property
    def run_timeout_s(self) -> int:
        """Per-run wall-clock budget from the OpenHands config -- the bridge
        uses it to bound how long it waits for a turn to reach a terminal
        status."""
        return self._cfg.run.timeout_s

    @property
    def context_window(self) -> int:
        """The served model's real context window (`configs/models.yaml`
        `ctx_size`). llama.cpp does not report it in its API responses, so the
        SDK's per-call `context_window` stays 0 -- the bridge uses this instead
        for the client's context gauge."""
        return get_settings().llm.ctx_size

    @property
    def read_only(self) -> bool:
        """Ask / Plan mode: the sandbox copy is still writable for the agent to
        experiment, but `apply_changes` is refused by the bridge."""
        return self._read_only

    @property
    def working_copy(self) -> WorkingCopy | None:
        """The disposable sandbox copy of the project (WP08d), or None when no
        project is mounted. Raises outside of a `with` block only via
        `.workspace`."""
        return self._working_copy

    def __enter__(self) -> AgentSession:
        _check_image_present(self._cfg.sandbox.image)
        _ensure_tools_registered()

        agent, model = _build_agent(self._cfg, self._mcp_config)

        if self._project_path is not None:
            if not self._project_path.is_dir():
                raise DependencyError(
                    f"project_path is not a directory: {self._project_path}",
                    details={"project_path": str(self._project_path)},
                )
            working_dir = _WORKING_COPY
            volumes = [f"{self._project_path}:{_PROJECT_SOURCE}:ro"]
        else:
            working_dir = self._cfg.sandbox.working_dir
            volumes = []

        workspace = AgenticEnvDockerWorkspace(
            server_image=self._cfg.sandbox.image,
            working_dir=working_dir,
            volumes=volumes,
            platform=self._cfg.sandbox.platform,
            enable_gpu=self._cfg.sandbox.enable_gpu,
            forward_env=["DEBUG"],
            detach_logs=True,
        )
        self._workspace = workspace

        conversation = Conversation(
            agent,
            workspace=workspace,
            visualizer=None,
            callbacks=self._callbacks,
            max_iteration_per_run=self._cfg.run.max_iterations,
            delete_on_close=True,
        )
        assert isinstance(conversation, RemoteConversation)
        self._conversation = conversation

        self._llm_source = _ensure_llm(conversation, agent, model, self._cfg.llm.sandbox_base_url)
        conversation.set_confirmation_policy(self._confirmation_policy)

        if self._project_path is not None:
            working_copy = WorkingCopy(workspace, _WORKING_COPY)
            working_copy.initialize()
            self._working_copy = working_copy

        logger.info(
            "agent session started",
            extra={
                "conversation_id": str(conversation.id),
                "llm_source": self._llm_source,
                "image": self._cfg.sandbox.image,
                "project_path": str(self._project_path) if self._project_path else None,
                "working_copy_git": self._working_copy.is_git if self._working_copy else None,
                "read_only": self._read_only,
            },
        )
        return self

    def send(self, message: str, *, blocking: bool = True) -> AgentResult | None:
        """Sends `message` and triggers a run.

        `blocking=True` (default, matches `run_task`'s batch usage) waits for
        the run to finish and returns the final `AgentResult`. `blocking=False`
        (used by packages/openhands-bridge for streaming) triggers the run and
        returns immediately with `None` -- the caller follows progress through
        the `callbacks` passed at construction and reads `self.conversation`/
        `self.workspace` once it observes a terminal `execution_status` itself.
        """
        conversation = self.conversation

        # mypy (2.3.1) misresolves RemoteConversation.send_message/.run in a way
        # that is non-deterministic across `just lint` runs (observed flipping
        # between "incompatible type Never" and "unused ignore" across runs with
        # no change to these lines) -- an upstream ABC/typing quirk, not a real
        # type error: both signatures are exactly as documented in
        # openhands/sdk/conversation/impl/remote_conversation.py
        # (send_message(self, message: str | Message, sender=None) -> None,
        # run(self, blocking=True, poll_interval=1.0, timeout=3600.0) -> None),
        # and both are exercised for real by the e2e smoke test. A `type:
        # ignore` is not viable here since mypy itself disagrees run to run on
        # whether it is needed; route through `Any` instead, which is stable.
        untyped_conversation = cast(Any, conversation)
        untyped_conversation.send_message(message)
        try:
            untyped_conversation.run(blocking=blocking, timeout=self._cfg.run.timeout_s)
        except ConversationRunError as exc:
            raise DependencyError(
                f"agent-server run failed: {exc}",
                details={"conversation_id": str(conversation.id)},
            ) from exc

        if not blocking:
            return None

        final_text = get_agent_final_response(conversation.state.events)
        return AgentResult(
            conversation_id=str(conversation.id),
            final_text=final_text,
            execution_status=conversation.state.execution_status.value,
            llm_source=self._llm_source,
        )

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._conversation is not None:
            try:
                self._conversation.close()
            except Exception:  # noqa: BLE001 - cleanup must not mask the real error
                logger.warning("failed to close conversation cleanly", exc_info=True)
        if self._workspace is not None:
            try:
                self._workspace.cleanup()
            except Exception:  # noqa: BLE001 - cleanup must not mask the real error
                logger.warning("failed to clean up sandbox workspace", exc_info=True)


def run_task(
    message: str,
    *,
    oh_config: OpenHandsConfig | None = None,
    confirmation_policy: ConfirmationPolicyBase | None = None,
    mcp_config: dict[str, object] | None = None,
    project_path: str | Path | None = None,
    read_only: bool = False,
) -> AgentResult:
    """Runs a single task end-to-end: open a sandbox, send `message`, tear down."""
    with AgentSession(
        oh_config=oh_config,
        confirmation_policy=confirmation_policy,
        mcp_config=mcp_config,
        project_path=project_path,
        read_only=read_only,
    ) as session:
        result = session.send(message, blocking=True)
        assert result is not None  # blocking=True always returns a result
        return result
