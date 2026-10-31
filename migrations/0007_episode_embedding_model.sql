-- WP14: vectors of two models can share a dimension and still mean nothing to each other,
-- so each episode records the model that embedded it, and `recall` compares like with like.
-- `embedding` is derived from the episode's text: rebuilding it does not rewrite the episode,
-- so A5 now covers everything else.
ALTER TABLE mem.episodes ADD COLUMN IF NOT EXISTS embedding_model text;

CREATE OR REPLACE FUNCTION mem.forbid_episode_update() RETURNS trigger AS $$
BEGIN
    IF (to_jsonb(NEW) - 'embedding' - 'embedding_model')
            = (to_jsonb(OLD) - 'embedding' - 'embedding_model') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'mem.episodes rows are immutable (WP07 rule A5); insert a new episode instead';
END;
$$ LANGUAGE plpgsql;

-- Every vector so far came from the only embedder that was ever configured.
UPDATE mem.episodes SET embedding_model = 'hashing-bow:1' WHERE embedding IS NOT NULL;
