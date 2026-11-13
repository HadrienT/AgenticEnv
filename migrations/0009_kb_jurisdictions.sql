-- WP21: the jurisdiction a regulatory text belongs to, and document types that tell
-- binding rules from guidance and proposals.
ALTER TABLE kb.documents DROP CONSTRAINT IF EXISTS documents_doc_type_check;
ALTER TABLE kb.documents ADD CONSTRAINT documents_doc_type_check CHECK (
    doc_type IN ('research_paper', 'book', 'documentation', 'standard', 'notes',
                 'law', 'guidance', 'proposal')
);

ALTER TABLE kb.documents ADD COLUMN IF NOT EXISTS jurisdiction text;

-- Backfill (2026-11-13 corpus): the Basel Framework chapters are international
-- standards; the four model-risk texts are supervisory guidance of their authority.
UPDATE kb.documents SET jurisdiction = 'intl'
    WHERE collection = 'regulation' AND starts_with(doc_key, 'bcbs-') AND jurisdiction IS NULL;
UPDATE kb.documents SET jurisdiction = 'us', doc_type = 'guidance'
    WHERE doc_key IN ('fed-sr-11-7-model-risk', 'fed-sr-26-2-model-risk');
UPDATE kb.documents SET jurisdiction = 'uk', doc_type = 'guidance'
    WHERE doc_key = 'pra-ss1-23-model-risk';
UPDATE kb.documents SET jurisdiction = 'eu', doc_type = 'guidance'
    WHERE doc_key = 'ecb-guide-internal-models-2024';

ALTER TABLE kb.documents DROP CONSTRAINT IF EXISTS documents_jurisdiction_check;
ALTER TABLE kb.documents ADD CONSTRAINT documents_jurisdiction_check CHECK (
    jurisdiction IN ('intl', 'eu', 'us', 'uk')
    AND collection = 'regulation'
    OR jurisdiction IS NULL AND collection <> 'regulation'
);
CREATE INDEX IF NOT EXISTS ix_documents_jurisdiction ON kb.documents (jurisdiction);
