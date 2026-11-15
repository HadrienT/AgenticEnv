-- What a tool call returned, in short (kb.search: the hits and their rerank scores), so
-- that `kbase usage` can tell what an agent searched for and whether it found it.
ALTER TABLE obs.tool_invocations ADD COLUMN IF NOT EXISTS result jsonb;

CREATE INDEX IF NOT EXISTS ix_tool_invocations_caller_ts ON obs.tool_invocations (caller, ts);
