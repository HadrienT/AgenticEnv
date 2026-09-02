# Task runner for AgenticEnv. Run `just --list` for the full list.

set dotenv-load := true

# Read-only hardware/OS inventory.
preflight:
    bash infra/scripts/preflight.sh

# Dump GPU topology into /opt/llm/gpu-topology.txt.
gpu-report:
    bash infra/scripts/gpu-report.sh

# Render /etc/llm/llama-server.env from configs/models.yaml (needs sudo to install).
render-llama-env:
    bash infra/scripts/render-llama-env.sh

# Aggregated health check, JSON on stdout, exit 0/1.
healthcheck:
    bash infra/scripts/healthcheck.sh

# Benchmark ctx_size values (8K/16K/32K/64K by default).
bench-context:
    bash infra/scripts/bench-context.sh

# Start the PostgreSQL container (pgvector + FTS).
db-up:
    docker compose -f infra/docker/compose.yaml up -d postgres

db-down:
    docker compose -f infra/docker/compose.yaml down

db-logs:
    docker compose -f infra/docker/compose.yaml logs -f postgres
