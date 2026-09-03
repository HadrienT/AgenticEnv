-- WP09 qmharness: eval schema (numerical run persistence). See
-- blueprint/04-DATA-MODEL.md and blueprint/wp/WP09-numerical-harness.md §2, §8.
CREATE SCHEMA IF NOT EXISTS eval;

CREATE TABLE IF NOT EXISTS eval.qm_runs (
    run_id              text PRIMARY KEY,
    mode                text NOT NULL CHECK (mode IN ('quick', 'standard', 'full')),
    started_at          timestamptz NOT NULL,
    ended_at            timestamptz NOT NULL,
    git_commit           text NOT NULL,
    build_preset        text NOT NULL,
    compiler            text NOT NULL,
    compiler_version    text NOT NULL,
    optimization        text NOT NULL,
    module_path         text NOT NULL,
    module_sha256       text NOT NULL,
    summary             jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_qm_runs_started_at ON eval.qm_runs (started_at);

CREATE TABLE IF NOT EXISTS eval.qm_case_results (
    id              text PRIMARY KEY,
    run_id          text NOT NULL REFERENCES eval.qm_runs (run_id) ON DELETE CASCADE,
    case_id         text NOT NULL,
    family          text NOT NULL CHECK (
        family IN ('golden', 'cross_engine', 'invariants', 'convergence', 'statistics', 'greeks')
    ),
    verdict         text NOT NULL CHECK (verdict IN ('pass', 'fail', 'warn')),
    message         text NOT NULL,
    observed        jsonb NOT NULL DEFAULT '{}'::jsonb,
    diff_abs        double precision,
    diff_rel        double precision,
    duration_ms     int NOT NULL,
    UNIQUE (run_id, case_id)
);

CREATE INDEX IF NOT EXISTS ix_qm_case_results_run_id ON eval.qm_case_results (run_id);
CREATE INDEX IF NOT EXISTS ix_qm_case_results_case_id ON eval.qm_case_results (case_id);
