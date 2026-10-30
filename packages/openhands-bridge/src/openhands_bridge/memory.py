"""The agent's memory across sessions (WP14 §2): what it learned is captured when a
session ends, without relying on it to call `mem.remember`, and recalled when the
next one starts. Everything here is best effort: memory never costs a session."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agentmem.config import load_agentmem_config
from agentmem.embeddings import build_embedder
from agentmem.episodic import recall, remember
from agentmem.schemas import Episode, EpisodeStatus
from corelib.config import get_settings
from corelib.errors import AppError
from corelib.logging import get_logger

logger = get_logger(__name__)

_RECALL_BUDGET_CHARS = 2000
_MAX_GOAL_CHARS = 500
_MAX_TRANSCRIPT_CHARS = 6000
_LLM_TIMEOUT_S = 300.0
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_SUMMARY_PROMPT = """You keep the long-term memory of a coding agent. From this session,
write what a future session should know. Answer with JSON only:
{"summary": "<two sentences on what was done and how it ended>",
 "lessons": ["<a reusable lesson, specific to this codebase or task>", ...],
 "tags": ["<lowercase topic>", ...]}
Give 1 to 4 lessons. Never include secrets, tokens or absolute file paths.

SESSION:
"""


@dataclass
class SessionDraft:
    """What the bridge saw of a session, kept until the episode is written."""

    conversation_id: str
    profile: str
    started_at: datetime
    project: str | None = None
    messages: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    last_reason: str = "completed"
    final_text: str = ""


def _status(reason: str) -> EpisodeStatus:
    return {"completed": "success", "cancelled": "abandoned"}.get(reason, "failure")  # type: ignore[return-value]


def _transcript(draft: SessionDraft) -> str:
    parts = [
        *(f"USER: {message}" for message in draft.messages),
        f"FILES CHANGED: {', '.join(draft.changed_files) or 'none'}",
        f"OUTCOME: {draft.last_reason}",
        f"AGENT'S LAST MESSAGE: {draft.final_text}",
    ]
    return "\n".join(parts)[-_MAX_TRANSCRIPT_CHARS:]


def _ask_llm(prompt: str) -> str:
    settings = get_settings().llm
    request = urllib.request.Request(
        f"{settings.base_url.rstrip('/')}/chat/completions",
        data=json.dumps(
            {
                "model": settings.served_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 500,
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=_LLM_TIMEOUT_S) as response:
        return str(json.load(response)["choices"][0]["message"]["content"])


def parse_summary(answer: str) -> dict[str, Any] | None:
    match = _JSON_RE.search(answer)
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(parsed, dict) or not parsed.get("summary") or not parsed.get("lessons"):
        return None
    return parsed


def record_episode(draft: SessionDraft, *, ended_at: datetime) -> str | None:
    """The episode's id, or None when the session left nothing worth keeping."""
    if not draft.messages:
        return None
    try:
        parsed = parse_summary(_ask_llm(_SUMMARY_PROMPT + _transcript(draft)))
        if parsed is None:
            logger.info("no usable session summary; nothing recorded")
            return None
        config = load_agentmem_config()
        tags = [str(tag) for tag in parsed.get("tags", [])]
        if draft.project:
            tags.append(draft.project)
        return remember(
            Episode(
                episode_id=uuid.uuid4().hex,
                task_id=draft.conversation_id,
                agent_profile=draft.profile,
                goal=draft.messages[0][:_MAX_GOAL_CHARS],
                started_at=draft.started_at,
                ended_at=ended_at,
                status=_status(draft.last_reason),
                summary=str(parsed["summary"]),
                lessons=[str(lesson) for lesson in parsed["lessons"]],
                tags=tags,
                outcome={"files_changed": draft.changed_files},
            ),
            embedder=build_embedder(config.embeddings),
            embed_summary=config.episodic.embed_summary,
        )
    except (AppError, urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        logger.warning("could not record the session episode: %s", exc)
        return None


def recall_context(text: str) -> str | None:
    """Past lessons relevant to `text`, as a prompt section, within a fixed budget."""
    try:
        config = load_agentmem_config()
        episodes = recall(
            text,
            k=config.episodic.recall_default_k,
            embedder=build_embedder(config.embeddings),
            min_similarity=config.episodic.min_similarity,
        )
    except (AppError, OSError) as exc:
        logger.info("memory recall unavailable: %s", exc)
        return None
    lines: list[str] = []
    used = 0
    for episode in episodes:
        line = f"- {episode.goal}: {' '.join(episode.lessons)}"
        if used + len(line) > _RECALL_BUDGET_CHARS:
            break
        lines.append(line)
        used += len(line)
    if not lines:
        return None
    return "<past_experience>\n" + "\n".join(lines) + "\n</past_experience>"
