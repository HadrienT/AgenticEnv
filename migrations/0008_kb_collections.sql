-- WP20: collections (separate corpora the agent picks from) and regulatory paragraph ids.
-- Every document ingested before WP20 belongs to the quant corpus.
ALTER TABLE kb.documents ADD COLUMN IF NOT EXISTS collection text;
UPDATE kb.documents SET collection = 'quant' WHERE collection IS NULL;
ALTER TABLE kb.documents ALTER COLUMN collection SET NOT NULL;
ALTER TABLE kb.documents DROP CONSTRAINT IF EXISTS documents_collection_check;
ALTER TABLE kb.documents ADD CONSTRAINT documents_collection_check
    CHECK (collection IN ('quant', 'regulation'));
CREATE INDEX IF NOT EXISTS ix_documents_collection ON kb.documents (collection);

-- `MAR21.4`, `Article 325c`: what a regulatory citation points to, stable across re-ingestion.
ALTER TABLE kb.chunks ADD COLUMN IF NOT EXISTS paragraph_ids text[] NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS ix_chunks_paragraph_ids ON kb.chunks USING gin (paragraph_ids);
