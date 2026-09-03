-- WP04 kbase.ingestion: kb schema (documents, versions, sections, chunks,
-- embeddings, equations, tables, ingestion_runs). See blueprint/04-DATA-MODEL.md §3.
CREATE SCHEMA IF NOT EXISTS kb;

CREATE TABLE IF NOT EXISTS kb.ingestion_runs (
    id                  uuid PRIMARY KEY,
    started_at          timestamptz NOT NULL,
    finished_at         timestamptz,
    status              text NOT NULL,
    config_sha          text NOT NULL,
    documents_seen       int NOT NULL DEFAULT 0,
    documents_ingested   int NOT NULL DEFAULT 0,
    chunks_written      int NOT NULL DEFAULT 0,
    errors              jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS kb.documents (
    id              uuid PRIMARY KEY,
    doc_key         text NOT NULL UNIQUE,
    title           text NOT NULL,
    authors         text[] NOT NULL DEFAULT '{}',
    year            int,
    doc_type        text NOT NULL CHECK (
                        doc_type IN ('research_paper', 'book', 'documentation', 'standard', 'notes')
                    ),
    topic           text,
    asset_class     text,
    source_url      text,
    license         text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kb.document_versions (
    id                  uuid PRIMARY KEY,
    document_id         uuid NOT NULL REFERENCES kb.documents (id) ON DELETE CASCADE,
    version             text NOT NULL,
    file_path           text NOT NULL,
    sha256              text NOT NULL UNIQUE,
    page_count          int,
    publication_date    date,
    ingestion_date      timestamptz NOT NULL,
    parser_name         text NOT NULL,
    parser_version      text NOT NULL,
    ingestion_run_id    uuid REFERENCES kb.ingestion_runs (id),
    status              text NOT NULL CHECK (status IN ('pending', 'parsed', 'indexed', 'failed'))
);

CREATE INDEX IF NOT EXISTS ix_document_versions_document_id
    ON kb.document_versions (document_id);

CREATE TABLE IF NOT EXISTS kb.sections (
    id                      uuid PRIMARY KEY,
    document_version_id     uuid NOT NULL REFERENCES kb.document_versions (id) ON DELETE CASCADE,
    parent_id               uuid REFERENCES kb.sections (id) ON DELETE CASCADE,
    level                   int NOT NULL,
    ordinal                 int NOT NULL,
    title                   text NOT NULL,
    page_start              int,
    page_end                int,
    path                    text NOT NULL,
    UNIQUE (document_version_id, path)
);

CREATE TABLE IF NOT EXISTS kb.chunks (
    id                      uuid PRIMARY KEY,
    document_version_id     uuid NOT NULL REFERENCES kb.document_versions (id) ON DELETE CASCADE,
    section_id              uuid REFERENCES kb.sections (id) ON DELETE SET NULL,
    ordinal                 int NOT NULL,
    kind                    text NOT NULL CHECK (kind IN ('text', 'equation', 'table', 'caption')),
    content                 text NOT NULL,
    n_tokens                int NOT NULL,
    page_start              int,
    page_end                int,
    has_equations           bool NOT NULL DEFAULT false,
    valid_from              date,
    valid_until             date,
    source_date             date,
    sha256                  text NOT NULL,
    search_tsv              tsvector,
    created_at              timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_version_id, ordinal)
);

CREATE INDEX IF NOT EXISTS ix_chunks_search_tsv ON kb.chunks USING GIN (search_tsv);
CREATE INDEX IF NOT EXISTS ix_chunks_has_equations ON kb.chunks (has_equations)
    WHERE has_equations;
CREATE INDEX IF NOT EXISTS ix_chunks_validity ON kb.chunks (valid_from, valid_until);

-- search_tsv: 'simple' config (no stemming) so SABR/SOFR/CVA survive intact
-- (blueprint/04-DATA-MODEL.md §6). Section title (weight A) is looked up by a
-- subquery since kb.chunks itself carries no denormalized title column.
CREATE OR REPLACE FUNCTION kb.chunks_search_tsv_trigger() RETURNS trigger AS $$
DECLARE
    section_title text;
BEGIN
    SELECT title INTO section_title FROM kb.sections WHERE id = NEW.section_id;
    NEW.search_tsv :=
        setweight(to_tsvector('simple', unaccent(coalesce(section_title, ''))), 'A')
        || setweight(to_tsvector('simple', unaccent(NEW.content)), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chunks_search_tsv ON kb.chunks;
CREATE TRIGGER trg_chunks_search_tsv
    BEFORE INSERT OR UPDATE ON kb.chunks
    FOR EACH ROW EXECUTE FUNCTION kb.chunks_search_tsv_trigger();

CREATE TABLE IF NOT EXISTS kb.chunk_embeddings (
    chunk_id        uuid NOT NULL REFERENCES kb.chunks (id) ON DELETE CASCADE,
    model_name      text NOT NULL,
    model_version   text NOT NULL,
    dim             int NOT NULL,
    embedding       vector(1024) NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id, model_name, model_version)
);

CREATE INDEX IF NOT EXISTS ix_chunk_embeddings_hnsw ON kb.chunk_embeddings
    USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS kb.equations (
    id                      uuid PRIMARY KEY,
    chunk_id                uuid NOT NULL REFERENCES kb.chunks (id) ON DELETE CASCADE,
    document_version_id     uuid NOT NULL REFERENCES kb.document_versions (id) ON DELETE CASCADE,
    latex                   text NOT NULL,
    equation_number         text,
    page                    int,
    symbols                 text[] NOT NULL DEFAULT '{}',
    context_before          text,
    context_after           text
);

CREATE INDEX IF NOT EXISTS ix_equations_symbols ON kb.equations USING GIN (symbols);
CREATE INDEX IF NOT EXISTS ix_equations_latex_trgm ON kb.equations USING GIN (latex gin_trgm_ops);

CREATE TABLE IF NOT EXISTS kb.tables (
    id              uuid PRIMARY KEY,
    chunk_id        uuid NOT NULL REFERENCES kb.chunks (id) ON DELETE CASCADE,
    caption         text,
    content_md      text NOT NULL,
    page            int
);

CREATE TABLE IF NOT EXISTS kb.retrieval_logs (
    id                  text PRIMARY KEY,
    ts                  timestamptz NOT NULL,
    query_text          text NOT NULL,
    filters             jsonb NOT NULL DEFAULT '{}'::jsonb,
    strategy            text NOT NULL,
    k                   int NOT NULL,
    latency_ms          int NOT NULL,
    result_chunk_ids    uuid[] NOT NULL DEFAULT '{}',
    scores              jsonb NOT NULL DEFAULT '{}'::jsonb,
    correlation_id      text
);

CREATE INDEX IF NOT EXISTS ix_retrieval_logs_ts ON kb.retrieval_logs (ts);

CREATE INDEX IF NOT EXISTS ix_documents_doc_key ON kb.documents (doc_key);
CREATE INDEX IF NOT EXISTS ix_documents_metadata
    ON kb.documents (doc_type, topic, asset_class, year);
