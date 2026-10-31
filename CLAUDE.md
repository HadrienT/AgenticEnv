# AgenticEnv — notes for Claude Code

**Local** agentic development workshop: `packages/openhands_adapter` (OpenHands SDK + Docker
sandbox driving `llama-server`), `packages/openhands-bridge` (WebSocket server exposed to a chat
client), the MCP servers (`*-mcp`), `corelib`.

**Twin repository**: [`agenticenv-chat`](https://github.com/HadrienT/agenticenv-chat), the VS Code
extension that talks to the bridge. The two evolve together; the wire protocol is
`packages/openhands-bridge/src/openhands_bridge/protocol.py`, manually mirrored in
`agenticenv-chat/src/protocol.ts` (drift test on the client side).

## Tracking work: GitHub Issues, no handoff markdown

The project's "JIRA" is the **GitHub Issues of both repositories**. `gh` is authenticated (account
`HadrienT`).

- **At the start of a session**: `gh issue list --state open` on **this repository** AND on
  `HadrienT/agenticenv-chat`. Each repository has a pinned **`📋 Board`** issue that aggregates
  everything (AgenticEnv#9, agenticenv-chat#3).
- **A task or bug concerning the other repository** →
  `gh issue create --repo HadrienT/agenticenv-chat …`. **Never** a markdown handoff file.
- **Issue handled** → `gh issue close <n> --repo … --comment "done in <sha>"`, and tick the matching
  box in the Board.
- **Labels**: `cross-repo` (coordination), `blocked` (waiting on the other repository),
  `needs-verification` (code done, a manual test remains), `from-bridge` / `from-client`.
- Large pieces of **design** stay in `blueprint/wp/*.md`; the issue points to them, it does not
  replace them.

## Commands

| | |
|---|---|
| `just lint` | ruff + `mypy --strict` per package + import-linter: **green before any commit** |
| `just test` | pytest (excluding `integration` / `e2e`) |
| `just test-integration` | with Postgres, on an `agenticenv_test` database rebuilt at each run (`conftest.py`) |
| `just bench-agent <label>` | agent benchmark (Docker + `llama-server`, several minutes per task) |
| `uv run kbase eval --label <x>` | retrieval measurement on `benchmarks/retrieval/queries.yaml` |
| `just test-e2e` | OpenHands smoke test (Docker + `llama-server` required, outside CI) |
| `just run-bridge` | runs the WebSocket bridge on `127.0.0.1:8300` |

## Miscellaneous

- **Language: English by default.** Everything you produce is in English: code, identifiers, comments, commit messages, PRs, issues, documentation and interface text. The only exception is the conversation: reply in the language the maintainer writes in, so in French when they write in French. `blueprint/` is historically in French: new content there is in English too.
- **Fragile Docker networking on the dev host**: a veth teardown on the default `docker0` bridge has
  already frozen the host and cut the whole LAN. Never a bulk `docker rm -f`; act one container at a
  time, explaining the blast radius. See issue #8.
- **The bridge in service runs from this checkout** (`agenticenv-bridge.service`): leave
  `~/AgenticEnv` on `main`, otherwise a restart loads unshipped code.
- Commits: go through a branch, not directly on `main`. End commit messages with
  `Co-Authored-By: Claude <noreply@anthropic.com>`.

## OpenHands sandbox (the agent running in the container)

Image `ghcr.io/openhands/agent-server:1.21.0-python` (Debian 13), **new at each session, discarded
at the end**. Provided: Python 3.13 + `uv`/pip/poetry, Node 20 + npm, `gcc`/`g++`/`make`, git,
`curl`/`wget`/`jq`, tmux, **passwordless `sudo`**, outbound Internet. Not provided: `cmake`, `rg`/`fd`,
`vim`, rust/go/java, or **CUDA**.

The agent installs what is missing by itself (it disappears at the end of the session):

- **nvcc / CUDA**: the `contrib non-free` component is not enabled by default.
  ```sh
  sudo sed -i 's/Components: main/Components: main contrib non-free/' \
    /etc/apt/sources.list.d/debian.sources
  sudo apt-get update && sudo apt-get install -y --no-install-recommends nvidia-cuda-toolkit
  ```
  ⚠️ ~2 GB, downloaded again at each session. nvcc **compiles** without a GPU; running CUDA code
  requires `enable_gpu: true` in `configs/openhands.yaml` (VRAM contention with `llama-server`).
- **Web**: no browsing tool (`enable_browser=False`); use `curl`/`wget`/`pip` in the terminal.
