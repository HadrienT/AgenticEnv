"""Episodic memory: write-once experience log (blueprint/03-INTERFACES.md §4, WP07 §2).

Deviation from the blueprint's placeholder signatures, same rationale as WP05's
`HybridRetriever`: `remember`/`recall` take an explicit `embedder` (+ threshold)
kwarg rather than reading `configs/agentmem.yaml` themselves, so the core library
stays config-free and unit-testable; only the CLI/MCP boundary loads the YAML.
`recall` also returns `EpisodeSummary` (never the action trace, per rule A6) —
the blueprint's own `list[Episode]` return type would violate its own A6."""

from __future__ import annotations

import re

from corelib.db import session_scope
from corelib.errors import ConfigError, NotFoundError, ValidationError
from corelib.ids import new_id
from corelib.serialization import to_json
from sqlalchemy import text
from sqlalchemy.orm import Session

from agentmem.embeddings import Embedder
from agentmem.schemas import Artifact, Episode, EpisodeAction, EpisodeSummary
from agentmem.secrets import find_forbidden_patterns

_VECTOR_DIM_RE = re.compile(r"vector\((\d+)\)")


def format_vector(values: list[float]) -> str:
    """pgvector's documented text input format: `[v1,v2,...]`."""
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def assert_dimension_matches(session: Session, expected_dim: int) -> None:
    """Boot-time guard: `configs/agentmem.yaml -> embeddings.dim` must equal `vector(D)`."""
    row = session.execute(
        text(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = 'mem.episodes'::regclass AND attname = 'embedding'"
        )
    ).first()
    if row is None:
        raise ConfigError("mem.episodes.embedding column not found", details={})
    match = _VECTOR_DIM_RE.search(row[0])
    if not match:
        raise ConfigError(
            f"could not parse vector dimension from {row[0]!r}", details={"type": row[0]}
        )
    db_dim = int(match.group(1))
    if db_dim != expected_dim:
        raise ConfigError(
            f"embeddings.dim={expected_dim} does not match mem.episodes vector({db_dim})",
            details={"configured_dim": expected_dim, "db_dim": db_dim},
        )


def _validate(episode: Episode) -> None:
    """A2 (summary/lessons mandatory) and A4 (no secret, no host path)."""
    if not episode.summary.strip():
        raise ValidationError("episode.summary must not be empty", details={})
    if not episode.lessons or not all(lesson.strip() for lesson in episode.lessons):
        raise ValidationError("episode.lessons must be non-empty", details={})
    findings = find_forbidden_patterns(episode.goal, episode.summary, *episode.lessons)
    if findings:
        raise ValidationError(
            "episode content matched a forbidden pattern (secret or host path)",
            details={"patterns": findings},
        )


def _insert_episode(session: Session, episode: Episode, embedding: list[float] | None) -> None:
    columns = (
        "episode_id, task_id, agent_profile, goal, started_at, ended_at, status, "
        "summary, outcome, lessons, tags, branch, last_commit"
    )
    values = (
        ":episode_id, :task_id, :agent_profile, :goal, :started_at, :ended_at, :status, "
        ":summary, CAST(:outcome AS jsonb), :lessons, :tags, :branch, :last_commit"
    )
    params: dict[str, object] = {
        "episode_id": episode.episode_id,
        "task_id": episode.task_id,
        "agent_profile": episode.agent_profile,
        "goal": episode.goal,
        "started_at": episode.started_at,
        "ended_at": episode.ended_at,
        "status": episode.status,
        "summary": episode.summary,
        "outcome": to_json(episode.outcome),
        "lessons": episode.lessons,
        "tags": episode.tags,
        "branch": episode.branch,
        "last_commit": episode.last_commit,
    }
    if embedding is not None:
        columns += ", embedding"
        values += ", CAST(:embedding AS vector)"
        params["embedding"] = format_vector(embedding)
    session.execute(text(f"INSERT INTO mem.episodes ({columns}) VALUES ({values})"), params)


def _insert_action(session: Session, episode_id: str, action: EpisodeAction) -> None:
    session.execute(
        text(
            "INSERT INTO mem.episode_actions "
            "(id, episode_id, ordinal, kind, name, args, result_summary, status, duration_ms) "
            "VALUES (:id, :episode_id, :ordinal, :kind, :name, CAST(:args AS jsonb), "
            " :result_summary, :status, :duration_ms)"
        ),
        {
            "id": new_id(),
            "episode_id": episode_id,
            "ordinal": action.ordinal,
            "kind": action.kind,
            "name": action.name,
            "args": to_json(action.args),
            "result_summary": action.result_summary,
            "status": action.status,
            "duration_ms": action.duration_ms,
        },
    )


def remember(episode: Episode, *, embedder: Embedder, embed_summary: bool = True) -> str:
    """Writes one episode + its actions/artifacts in a single transaction (A1/A2/A4/A5).
    The embedding (when `embed_summary`) covers `goal + summary + lessons` only (A3),
    never the action trace."""
    _validate(episode)

    embedding: list[float] | None = None
    if embed_summary:
        embedding = list(
            embedder.embed("\n".join([episode.goal, episode.summary, *episode.lessons]))
        )

    with session_scope() as session:
        _insert_episode(session, episode, embedding)
        for action in episode.actions:
            _insert_action(session, episode.episode_id, action)
        for artifact in episode.artifacts:
            session.execute(
                text(
                    "INSERT INTO mem.artifacts (id, episode_id, kind, path, sha256) "
                    "VALUES (:id, :episode_id, :kind, :path, :sha256)"
                ),
                {
                    "id": new_id(),
                    "episode_id": episode.episode_id,
                    "kind": artifact.kind,
                    "path": artifact.path,
                    "sha256": artifact.sha256,
                },
            )
    return episode.episode_id


def recall(
    query: str,
    *,
    k: int,
    tags: list[str] | None = None,
    status: str | None = None,
    embedder: Embedder,
    min_similarity: float,
) -> list[EpisodeSummary]:
    """Vector recall over `goal + summary + lessons` embeddings, gated by
    `min_similarity` (rule: better to return nothing than an off-topic episode).
    Never returns the action trace (A6)."""
    vector = format_vector(list(embedder.embed(query)))
    clauses = ["embedding IS NOT NULL"]
    params: dict[str, object] = {"embedding": vector, "k": k, "min_similarity": min_similarity}
    if tags:
        clauses.append("tags && CAST(:tags AS text[])")
        params["tags"] = tags
    if status:
        clauses.append("status = :status")
        params["status"] = status
    clauses.append("1 - (embedding <=> CAST(:embedding AS vector)) >= :min_similarity")
    where = " AND ".join(clauses)

    with session_scope() as session:
        rows = session.execute(
            text(
                "SELECT episode_id, task_id, agent_profile, goal, started_at, ended_at, status, "
                " summary, outcome, lessons, tags, branch, last_commit, "
                " 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity "
                f"FROM mem.episodes WHERE {where} ORDER BY similarity DESC LIMIT :k"
            ),
            params,
        ).all()

    return [
        EpisodeSummary(
            episode_id=row.episode_id,
            task_id=row.task_id,
            agent_profile=row.agent_profile,
            goal=row.goal,
            started_at=row.started_at,
            ended_at=row.ended_at,
            status=row.status,
            summary=row.summary,
            outcome=dict(row.outcome or {}),
            lessons=list(row.lessons or []),
            tags=list(row.tags or []),
            branch=row.branch,
            last_commit=row.last_commit,
            similarity=float(row.similarity),
        )
        for row in rows
    ]


def get_episode(episode_id: str) -> Episode:
    """Full detail, including the action trace — not exposed through MCP (only used
    internally / for audits), unlike the intentionally-summarized `recall`."""
    with session_scope() as session:
        row = session.execute(
            text(
                "SELECT episode_id, task_id, agent_profile, goal, started_at, ended_at, status, "
                " summary, outcome, lessons, tags, branch, last_commit "
                "FROM mem.episodes WHERE episode_id = :episode_id"
            ),
            {"episode_id": episode_id},
        ).first()
        if row is None:
            raise NotFoundError("episode not found", details={"episode_id": episode_id})

        action_rows = session.execute(
            text(
                "SELECT ordinal, kind, name, args, result_summary, status, duration_ms "
                "FROM mem.episode_actions WHERE episode_id = :episode_id ORDER BY ordinal"
            ),
            {"episode_id": episode_id},
        ).all()
        artifact_rows = session.execute(
            text("SELECT kind, path, sha256 FROM mem.artifacts WHERE episode_id = :episode_id"),
            {"episode_id": episode_id},
        ).all()

    actions = [
        EpisodeAction(
            ordinal=a.ordinal,
            kind=a.kind,
            name=a.name,
            args=dict(a.args or {}),
            result_summary=a.result_summary,
            status=a.status,
            duration_ms=a.duration_ms,
        )
        for a in action_rows
    ]
    artifacts = [Artifact(kind=a.kind, path=a.path, sha256=a.sha256) for a in artifact_rows]

    return Episode(
        episode_id=row.episode_id,
        task_id=row.task_id,
        agent_profile=row.agent_profile,
        goal=row.goal,
        started_at=row.started_at,
        ended_at=row.ended_at,
        status=row.status,
        summary=row.summary,
        actions=actions,
        outcome=dict(row.outcome or {}),
        lessons=list(row.lessons or []),
        tags=list(row.tags or []),
        branch=row.branch,
        last_commit=row.last_commit,
        artifacts=artifacts,
    )
