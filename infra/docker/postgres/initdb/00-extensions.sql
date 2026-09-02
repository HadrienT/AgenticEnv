-- Extensions required by kbase (pgvector) and lexical search (pg_trgm, unaccent).
-- Applied once at container init; subsequent schema changes live in migrations/.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
