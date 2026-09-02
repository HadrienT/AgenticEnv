# Development sandbox for the coding agent. Non-root, /workspace only.
FROM debian:trixie-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl wget ca-certificates \
        build-essential cmake ninja-build pkg-config \
        python3 python3-pip python3-venv \
        nodejs npm \
        jq ripgrep fd-find unzip zip \
    && rm -rf /var/lib/apt/lists/*

ARG SANDBOX_UID=10001
ARG SANDBOX_GID=10001
RUN groupadd -g "${SANDBOX_GID}" sandbox \
    && useradd -m -u "${SANDBOX_UID}" -g "${SANDBOX_GID}" -s /bin/bash sandbox

WORKDIR /workspace
RUN chown sandbox:sandbox /workspace
USER sandbox

COPY --chown=sandbox:sandbox entrypoint.sh /usr/local/bin/entrypoint.sh
USER root
RUN chmod +x /usr/local/bin/entrypoint.sh
USER sandbox

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
