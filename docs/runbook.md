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

## OpenHands (WP08)

One-time install:

```bash
uv tool install openhands --python 3.12   # ~/.local/bin/openhands (+ openhands-acp)
export PATH="$HOME/.local/bin:$PATH"      # add to shell profile
export OPENHANDS_SUPPRESS_BANNER=1        # required for scripted/headless use
```

Render LLM + MCP config (idempotent, safe to re-run after changing
`configs/models.yaml` or `configs/mcp/*.yaml`, or after restarting `llama-server`):

```bash
bash infra/scripts/render-openhands-config.sh
openhands mcp list      # confirm all 4 servers (agentmem, codeintel, cppdev, kbase) enabled
```

Run a task (CLI headless — **no Docker sandbox in this mode**, see
`blueprint/wp/WP08-openhands-integration.md` §5 for why, and what mitigates it):

```bash
cd /srv/repos/<project>            # never run from a directory with secrets/credentials
openhands --headless --json -t "..." > /tmp/run.jsonl 2>/tmp/run.err
```

Apply the reusable hooks/skills template to a new target repo before any
autonomous task (blocks `git push`/merge/force/`reset --hard`/`rm -rf` and secret
paths via a `PreToolUse` hook — required since headless mode always auto-approves):

```bash
cp -r agents/openhands-template/.openhands agents/openhands-template/.agents \
      agents/openhands-template/AGENTS.md.template /srv/repos/<project>/
mv /srv/repos/<project>/AGENTS.md.template /srv/repos/<project>/AGENTS.md
# then edit AGENTS.md with real repo content, per agents/openhands-template/README.md
```

## Incidents

| Symptom | Likely cause | Action |
|---|---|---|
| `render-llama-env.sh` fails on sha256 | GGUF not downloaded or corrupted | re-download, recompute `sha256sum`, update `configs/models.yaml` |
| `render-llama-env.sh` fails on ctx_size | value not benchmarked | run `bench-context.sh`, add the value to `validated_ctx_sizes` |
| `healthcheck.sh` reports `no_cpu_offload: critical` | model spilled to CPU/RAM | reduce `ctx_size` or quantization — never enable offload |
| `docker_gpus: error` | NVIDIA Container Toolkit not configured | `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker` |
| `postgres: critical` | container not started | `just db-up`, then `docker compose -f infra/docker/compose.yaml logs postgres` |
| OpenHands MCP server crashes with `corelib.errors.ConfigError` at startup | registered with `uv run --project` instead of `--directory` — `corelib.config.Settings` resolves `.env` relative to CWD | re-run `render-openhands-config.sh` (uses `--directory`) |
| OpenHands MCP client raises `pydantic_core.ValidationError` parsing a JSONRPC message | a server logged to stdout, corrupting the stdio JSON-RPC stream | ensure `corelib.logging` writes to stderr (already the case; check for stray `print()` in any new MCP server code) |

## Absolute prohibitions (see blueprint/00-PRIMER.md §5)

Never install CUDA 13 or NVIDIA open kernel modules on these V100s. Never enable
CPU offload for model weights. Never bind `llama-server`, PostgreSQL, or an MCP
server to `0.0.0.0` without an explicit request. Never mount `/`, `/etc`, `/home`,
or `~/.ssh` into the sandbox.
