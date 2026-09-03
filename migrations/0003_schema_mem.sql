-- WP07 agentmem: mem schema (episodic + procedural memory). See
-- blueprint/04-DATA-MODEL.md §4 and blueprint/wp/WP07-agentmem.md.
CREATE SCHEMA IF NOT EXISTS mem;

CREATE TABLE IF NOT EXISTS mem.episodes (
    episode_id      text PRIMARY KEY,
    task_id         text NOT NULL,
    agent_profile   text NOT NULL,
    goal            text NOT NULL,
    started_at      timestamptz NOT NULL,
    ended_at        timestamptz NOT NULL,
    status          text NOT NULL CHECK (status IN ('success', 'failure', 'partial', 'abandoned')),
    summary         text NOT NULL CHECK (btrim(summary) <> ''),
    outcome         jsonb NOT NULL DEFAULT '{}'::jsonb,
    lessons         text[] NOT NULL CHECK (array_length(lessons, 1) > 0),
    tags            text[] NOT NULL DEFAULT '{}',
    branch          text,
    last_commit     text,
    embedding       vector(256),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_episodes_embedding ON mem.episodes
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS ix_episodes_tags ON mem.episodes USING GIN (tags);

-- A5: an episode is immutable once written. A correction is a new episode, never an UPDATE.
CREATE OR REPLACE FUNCTION mem.forbid_episode_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'mem.episodes rows are immutable (WP07 rule A5); insert a new episode instead';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_episodes_immutable ON mem.episodes;
CREATE TRIGGER trg_episodes_immutable
    BEFORE UPDATE ON mem.episodes
    FOR EACH ROW EXECUTE FUNCTION mem.forbid_episode_update();

CREATE TABLE IF NOT EXISTS mem.episode_actions (
    id              text PRIMARY KEY,
    episode_id      text NOT NULL REFERENCES mem.episodes (episode_id) ON DELETE CASCADE,
    ordinal         int NOT NULL,
    kind            text NOT NULL CHECK (kind IN ('tool', 'llm', 'human')),
    name            text NOT NULL,
    args            jsonb NOT NULL DEFAULT '{}'::jsonb,
    result_summary  text NOT NULL,
    status          text NOT NULL,
    duration_ms     int NOT NULL,
    UNIQUE (episode_id, ordinal)
);

CREATE INDEX IF NOT EXISTS ix_episode_actions_episode_id ON mem.episode_actions (episode_id);

CREATE TABLE IF NOT EXISTS mem.artifacts (
    id              text PRIMARY KEY,
    episode_id      text NOT NULL REFERENCES mem.episodes (episode_id) ON DELETE CASCADE,
    kind            text NOT NULL,
    path            text NOT NULL,
    sha256          text NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_artifacts_episode_id ON mem.artifacts (episode_id);

-- Source of truth is Git (agents/procedures/*.yaml); this table is a queryable
-- cache rebuilt by agentmem.procedural.sync_from_git() (A7/A8/A9).
CREATE TABLE IF NOT EXISTS mem.procedures (
    name            text NOT NULL,
    version         text NOT NULL,
    description     text NOT NULL,
    preconditions   text[] NOT NULL DEFAULT '{}',
    postconditions  text[] NOT NULL DEFAULT '{}',
    steps           jsonb NOT NULL,
    tags            text[] NOT NULL DEFAULT '{}',
    source_path     text NOT NULL,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (name, version)
);

CREATE INDEX IF NOT EXISTS ix_procedures_tags ON mem.procedures USING GIN (tags);
