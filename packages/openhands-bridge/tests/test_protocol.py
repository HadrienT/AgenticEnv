from __future__ import annotations

import pytest
from corelib.errors import ValidationError
from openhands_bridge.protocol import (
    ConfirmAction,
    ErrorMessage,
    ListMcpServers,
    McpServerEntry,
    McpServers,
    StartSession,
    UserMessage,
    parse_inbound,
    serialize_outbound,
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
