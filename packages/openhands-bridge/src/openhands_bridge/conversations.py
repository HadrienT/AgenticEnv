"""What the bridge remembers of each conversation across restarts (WP08e): enough to start
its sandbox again and to list it. The conversation itself lives with the agent-server."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from openhands_adapter import persistence_dir

_TITLE_LENGTH = 80


class ConversationRecord(BaseModel):
    conversation_id: str
    project_path: str | None = None
    mode: str = "agent"
    profile: str | None = None
    mcp_servers: list[str] = Field(default_factory=list)
    title: str | None = None
    updated_at: str = ""
    turns: int = 0
    seq: int = 0
    archived: bool = False


def _index() -> Path:
    return persistence_dir() / "index.json"


def _read() -> dict[str, ConversationRecord]:
    try:
        raw = json.loads(_index().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {key: ConversationRecord.model_validate(value) for key, value in raw.items()}


def _write(records: dict[str, ConversationRecord]) -> None:
    path = _index()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({key: value.model_dump() for key, value in records.items()}, indent=1),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def get(conversation_id: str) -> ConversationRecord | None:
    return _read().get(conversation_id)


def save(record: ConversationRecord) -> None:
    records = _read()
    records[record.conversation_id] = record.model_copy(update={"updated_at": _now()})
    _write(records)


def note_turn(conversation_id: str, text: str, seq: int) -> None:
    """After a turn: the first message names the conversation."""
    records = _read()
    record = records.get(conversation_id)
    if record is None:
        return
    record.title = record.title or text[:_TITLE_LENGTH]
    record.turns += 1
    record.seq = seq
    record.updated_at = _now()
    _write(records)


def archive(conversation_id: str) -> bool:
    records = _read()
    record = records.get(conversation_id)
    if record is None:
        return False
    record.archived = True
    _write(records)
    return True


def listed() -> list[ConversationRecord]:
    """Most recent first, the archived ones left out."""
    records = [record for record in _read().values() if not record.archived]
    return sorted(records, key=lambda record: record.updated_at, reverse=True)
