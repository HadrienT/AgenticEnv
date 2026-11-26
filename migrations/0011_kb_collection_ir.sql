-- The `ir` collection: retrieval, RAG, document parsing and MCP papers, kept apart from
-- the quant and regulation corpora the agents search for their own work.
ALTER TABLE kb.documents DROP CONSTRAINT IF EXISTS documents_collection_check;
ALTER TABLE kb.documents ADD CONSTRAINT documents_collection_check
    CHECK (collection IN ('quant', 'regulation', 'ir'));
