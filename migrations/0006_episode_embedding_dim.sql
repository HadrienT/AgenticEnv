-- WP14: episodes use the same 1024-dimension models as the knowledge base. Vectors
-- of another size cannot be cast: an embedding is rebuilt from the episode's text.
DROP INDEX IF EXISTS mem.ix_episodes_embedding;
UPDATE mem.episodes SET embedding = NULL;
ALTER TABLE mem.episodes ALTER COLUMN embedding TYPE vector(1024);
CREATE INDEX IF NOT EXISTS ix_episodes_embedding ON mem.episodes
    USING hnsw (embedding vector_cosine_ops);
