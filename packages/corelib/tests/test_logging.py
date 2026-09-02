from __future__ import annotations

import json
import logging

from corelib.logging import bind_correlation_id, get_logger


def test_correlation_id_present_in_all_logs_within_block() -> None:
    logger = get_logger("test.correlation")
    stream_handler = logging.getLogger().handlers[0]
    records: list[str] = []
    original_emit = stream_handler.emit

    def capture(record: logging.LogRecord) -> None:
        records.append(stream_handler.format(record))

    stream_handler.emit = capture  # type: ignore[method-assign]
    try:
        with bind_correlation_id("cid-123"):
            logger.info("first")
            logger.info("second")
        logger.info("outside")
    finally:
        stream_handler.emit = original_emit  # type: ignore[method-assign]

    payloads = [json.loads(r) for r in records]
    assert payloads[0]["correlation_id"] == "cid-123"
    assert payloads[1]["correlation_id"] == "cid-123"
    assert "correlation_id" not in payloads[2]


def test_get_logger_emits_json_with_required_fields() -> None:
    logger = get_logger("test.fields")
    stream_handler = logging.getLogger().handlers[0]
    captured = {}

    def capture(record: logging.LogRecord) -> None:
        captured["line"] = stream_handler.format(record)

    original_emit = stream_handler.emit
    stream_handler.emit = capture  # type: ignore[method-assign]
    try:
        logger.info("hello", extra={"duration_ms": 42})
    finally:
        stream_handler.emit = original_emit  # type: ignore[method-assign]

    payload = json.loads(captured["line"])
    assert payload["msg"] == "hello"
    assert payload["logger"] == "test.fields"
    assert payload["level"] == "INFO"
    assert payload["duration_ms"] == 42
    assert "ts" in payload
