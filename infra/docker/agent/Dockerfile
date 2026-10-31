# The sandbox image with what the base lacks (WP17 §6): the C++ tools the agent would
# otherwise reinstall each session, and the code MCP servers, which must run next to
# the copy they read. Build with `just build-agent-image`, then set in
# configs/openhands.yaml: sandbox.image: agenticenv/agent:latest, sandbox.code_tools: true.
FROM ghcr.io/openhands/agent-server:1.21.0-python@sha256:9853a9eb75dfe42837b64d3b61a05f3c1f25549ecde39a89f703dbf92c87dca9

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        cmake ninja-build ripgrep fd-find clangd clang-format clang-tidy gcovr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/agenticenv
COPY pyproject.toml uv.lock .python-version ./
COPY packages ./packages
COPY configs ./configs
COPY benchmarks/golden ./benchmarks/golden
RUN uv sync --frozen --no-dev \
        --package cppdev-mcp --package codeintel-mcp --package qmharness-mcp

USER openhands
WORKDIR /workspace
