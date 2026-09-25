from __future__ import annotations

import pytest
from corelib.errors import ValidationError
from openhands_bridge.protocol import (
    CAPABILITIES,
    PROTOCOL_VERSION,
    ApplyChanges,
    CancelTurn,
    ConfirmAction,
    DiscardChanges,
    ErrorMessage,
    Hello,
    ListMcpServers,
    McpServerEntry,
    McpServers,
    RequestBundleDiff,
    RestoreCheckpoint,
    StartSession,
    TurnFinished,
    UserMessage,
    Welcome,
    parse_inbound,
    serialize_outbound,
    truncate,
)


def test_parse_inbound_start_session_with_mcp_servers() -> None:
    message = parse_inbound('{"type": "start_session", "mcp_servers": ["kbase", "agentmem"]}')

    assert isinstance(message, StartSession)
    assert message.mcp_servers == ["kbase", "agentmem"]


def test_parse_inbound_start_session_defaults_mcp_servers_to_empty() -> None:
    message = parse_inbound('{"type": "start_session"}')

    assert isinstance(message, StartSession)
    assert message.mcp_servers == []
    assert message.project_path is None


def test_parse_inbound_start_session_with_project_path() -> None:
    message = parse_inbound('{"type": "start_session", "project_path": "/srv/repos/x"}')

    assert isinstance(message, StartSession)
    assert message.project_path == "/srv/repos/x"


def test_parse_inbound_user_message() -> None:
    message = parse_inbound('{"type": "user_message", "text": "hello"}')

    assert isinstance(message, UserMessage)
    assert message.text == "hello"


def test_parse_inbound_confirm_action() -> None:
    message = parse_inbound('{"type": "confirm_action", "accept": false}')

    assert isinstance(message, ConfirmAction)
    assert message.accept is False


def test_parse_inbound_list_mcp_servers() -> None:
    assert isinstance(parse_inbound('{"type": "list_mcp_servers"}'), ListMcpServers)


def test_parse_inbound_unknown_type_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        parse_inbound('{"type": "not_a_real_type"}')


def test_serialize_outbound_mcp_servers() -> None:
    raw = serialize_outbound(
        McpServers(
            servers=[McpServerEntry(name="kbase", transport="stdio", tools_allowlist=["kb.x"])]
        )
    )

    assert '"type":"mcp_servers"' in raw
    assert '"name":"kbase"' in raw


def test_parse_inbound_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        parse_inbound('{"type": "user_message", "text": "hi", "extra": "nope"}')


def test_serialize_outbound_error_message_round_trips() -> None:
    raw = serialize_outbound(
        ErrorMessage(code="NO_SESSION", message="Send start_session first.", details={"a": 1})
    )

    assert '"type":"error"' in raw
    assert '"code":"NO_SESSION"' in raw


# --- v2 negotiation + WP08d ------------------------------------------------


def test_parse_inbound_hello() -> None:
    message = parse_inbound('{"type": "hello", "protocol": 2, "client": "agenticenv-chat/0.4.0"}')

    assert isinstance(message, Hello)
    assert message.protocol == 2
    assert message.client == "agenticenv-chat/0.4.0"


def test_welcome_defaults_advertise_this_bridge() -> None:
    welcome = Welcome()

    assert welcome.protocol == PROTOCOL_VERSION
    assert welcome.capabilities == list(CAPABILITIES)
    assert "apply" in welcome.capabilities
    assert "checkpoints" in welcome.capabilities


def test_outbound_seq_defaults_to_none_and_is_stampable() -> None:
    finished = TurnFinished(turn_id="t1", reason="completed")
    assert finished.seq is None

    finished.seq = 7
    assert '"seq":7' in serialize_outbound(finished)


def test_parse_inbound_start_session_mode_defaults_to_agent() -> None:
    message = parse_inbound('{"type": "start_session"}')

    assert isinstance(message, StartSession)
    assert message.mode == "agent"


def test_parse_inbound_start_session_read_only_mode() -> None:
    message = parse_inbound('{"type": "start_session", "mode": "read_only"}')

    assert isinstance(message, StartSession)
    assert message.mode == "read_only"


def test_parse_inbound_start_session_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        parse_inbound('{"type": "start_session", "mode": "banana"}')


def test_parse_inbound_user_message_with_context() -> None:
    message = parse_inbound(
        '{"type": "user_message", "text": "fix it", "context": ['
        '{"kind": "file", "label": "a.py", "body": "x = 1", "truncated": false}]}'
    )

    assert isinstance(message, UserMessage)
    assert message.context[0].kind == "file"
    assert message.context[0].label == "a.py"


def test_parse_inbound_cancel_turn() -> None:
    message = parse_inbound('{"type": "cancel_turn", "turn_id": "abc123"}')

    assert isinstance(message, CancelTurn)
    assert message.turn_id == "abc123"


def test_parse_inbound_apply_changes_defaults() -> None:
    message = parse_inbound('{"type": "apply_changes"}')

    assert isinstance(message, ApplyChanges)
    assert message.paths is None
    assert message.force is False


def test_parse_inbound_apply_changes_with_paths_and_force() -> None:
    message = parse_inbound('{"type": "apply_changes", "paths": ["a.py"], "force": true}')

    assert isinstance(message, ApplyChanges)
    assert message.paths == ["a.py"]
    assert message.force is True


def test_parse_inbound_request_bundle_diff_and_restore_and_discard() -> None:
    assert isinstance(parse_inbound('{"type": "request_bundle_diff"}'), RequestBundleDiff)
    assert isinstance(
        parse_inbound('{"type": "restore_checkpoint", "checkpoint_id": "c1"}'),
        RestoreCheckpoint,
    )
    assert isinstance(parse_inbound('{"type": "discard_changes"}'), DiscardChanges)


def test_truncate_passes_small_payloads_through() -> None:
    text, was_truncated = truncate("small")

    assert text == "small"
    assert was_truncated is False


def test_truncate_clips_oversized_payloads() -> None:
    text, was_truncated = truncate("x" * (300 * 1024))

    assert was_truncated is True
    assert len(text.encode("utf-8")) <= 256 * 1024
