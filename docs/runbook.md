# Runbook — AgenticEnv infrastructure (WP00)

## Startup order (locked, see blueprint/05-SEQUENCES.md §1)

PostgreSQL → llama-server → MCP servers → OpenHands. Each step is blocking.

```bash
just db-up                          # PostgreSQL (docker compose)
sudo systemctl start llama-server   # llama.cpp server
sudo systemctl start mcp-cppdev mcp-kbase mcp-agentmem mcp-codeintel mcp-qmharness
just healthcheck                    # must exit 0 before starting OpenHands
```

## One-time host setup (requires sudo, run manually)

```bash
# 1. system directories
sudo mkdir -p /opt/llm/{models,logs,scripts} /opt/agents /srv/sandboxes /srv/repos
sudo chown "$USER":"$USER" /opt/llm /opt/llm/models /opt/llm/logs

# 2. deploy scripts read by systemd units (source of truth stays in infra/scripts/)
sudo mkdir -p /opt/llm/scripts
sudo cp infra/scripts/run-llama-server.sh /opt/llm/scripts/run-llama-server.sh
sudo chmod +x /opt/llm/scripts/run-llama-server.sh

# 3. system user for the llama-server service
sudo useradd --system --no-create-home --shell /usr/sbin/nologin llm || true

# 4. render env + install systemd units
sudo mkdir -p /etc/llm
infra/scripts/render-llama-env.sh          # writes /tmp/llama-server.env.generated if not run as root
sudo install -m 0644 /tmp/llama-server.env.generated /etc/llm/llama-server.env
sudo cp infra/systemd/llama-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now llama-server
```

## Changing model or context size

```bash
# edit configs/models.yaml: active / ctx_size
infra/scripts/render-llama-env.sh
sudo install -m 0644 /tmp/llama-server.env.generated /etc/llm/llama-server.env
sudo systemctl restart llama-server
infra/scripts/healthcheck.sh
```

`ctx_size` must already be present in `configs/models.yaml:validated_ctx_sizes`
(populate this list by running `infra/scripts/bench-context.sh` first).

## Incidents

| Symptom | Likely cause | Action |
|---|---|---|
| `render-llama-env.sh` fails on sha256 | GGUF not downloaded or corrupted | re-download, recompute `sha256sum`, update `configs/models.yaml` |
| `render-llama-env.sh` fails on ctx_size | value not benchmarked | run `bench-context.sh`, add the value to `validated_ctx_sizes` |
| `healthcheck.sh` reports `no_cpu_offload: critical` | model spilled to CPU/RAM | reduce `ctx_size` or quantization — never enable offload |
| `docker_gpus: error` | NVIDIA Container Toolkit not configured | `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker` |
| `postgres: critical` | container not started | `just db-up`, then `docker compose -f infra/docker/compose.yaml logs postgres` |

## Absolute prohibitions (see blueprint/00-PRIMER.md §5)

Never install CUDA 13 or NVIDIA open kernel modules on these V100s. Never enable
CPU offload for model weights. Never bind `llama-server`, PostgreSQL, or an MCP
server to `0.0.0.0` without an explicit request. Never mount `/`, `/etc`, `/home`,
or `~/.ssh` into the sandbox.
