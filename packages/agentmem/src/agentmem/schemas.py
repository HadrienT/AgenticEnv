"""Domain schemas for agentmem (blueprint/03-INTERFACES.md §4, WP07 §2-§3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EpisodeStatus = Literal["success", "failure", "partial", "abandoned"]
ActionKind = Literal["tool", "llm", "human"]


class EpisodeAction(BaseModel):
    ordinal: int
    kind: ActionKind
    name: str
    args: dict[str, Any] = Field(default_factory=dict)  # tool call args, shape is per-tool
    result_summary: str
    status: str
    duration_ms: int


class Artifact(BaseModel):
    kind: str
    path: str
    sha256: str


class Episode(BaseModel):
    """One immutable trace of a finished task (A5). `actions` is the full trace,
    never returned by `recall` (A6) — only exposed via `get_episode`, which itself
    is not an MCP tool."""

    episode_id: str
    task_id: str
    agent_profile: str
    goal: str
    started_at: datetime
    ended_at: datetime
    status: EpisodeStatus
    summary: str
    actions: list[EpisodeAction] = Field(default_factory=list)
    outcome: dict[str, Any] = Field(default_factory=dict)  # structured result, per-task shape
    lessons: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    branch: str | None = None
    last_commit: str | None = None
    artifacts: list[Artifact] = Field(default_factory=list)


class EpisodeSummary(BaseModel):
    """What `recall` returns (A6): everything except the action trace, plus the
    similarity score that produced the ranking."""

    episode_id: str
    task_id: str
    agent_profile: str
    goal: str
    started_at: datetime
    ended_at: datetime
    status: EpisodeStatus
    summary: str
    outcome: dict[str, Any]
    lessons: list[str]
    tags: list[str]
    branch: str | None
    last_commit: str | None
    similarity: float


class ProcedureStep(BaseModel):
    objective: str
    verification: str


class Procedure(BaseModel):
    name: str
    version: str
    description: str
    preconditions: list[str] = Field(default_factory=list)
    steps: list[ProcedureStep]
    postconditions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source_path: str  # Git path, source of truth (A7/A9)


class ProcedureSummary(BaseModel):
    name: str
    version: str
    description: str
    tags: list[str]
    source_path: str


class SyncReport(BaseModel):
    synced: int
    removed: int
    errors: list[str]
